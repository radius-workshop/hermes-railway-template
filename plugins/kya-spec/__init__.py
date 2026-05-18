"""KYA / PAY / KYA-PAY token verification plugin.

Verifies tokens issued under the KYAPay specification (https://kyapay.org):

    1. Decode the JWT header and payload.
    2. Resolve the issuer's JWKS at ``{iss}/.well-known/jwks.json``.
    3. Match the header ``kid`` against a JWKS entry.
    4. Verify the JWT signature with the matched key (ES256 only, per the
       current public spec).
    5. Enforce claim shape, REQUIRED/OPTIONAL semantics, timestamp validity,
       audience binding, environment binding, and a trusted-issuer allowlist.
    6. Track ``jti`` in an in-memory LRU to mitigate replay.

This plugin exposes one tool: ``kya_validate_claims``.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Spec constants — sourced from https://kyapay.org/specifications
# ---------------------------------------------------------------------------

GENERAL_REQUIRED_HEADER = {"alg", "kid", "typ"}
GENERAL_REQUIRED_PAYLOAD = {"iss", "sub", "aud", "iat", "jti", "exp"}
TYP_ALLOWED = {"kya+jwt", "pay+jwt", "kya-pay+jwt"}

# Per current public spec: "currently ES256". Update when the spec adds algos.
SUPPORTED_JWA = {"ES256"}

# Sub-claim requirements when the parent object is present.
HID_REQUIRED_WHEN_PRESENT = {"email"}
APD_REQUIRED_WHEN_PRESENT = {"id", "name"}
AID_REQUIRED = {"name", "creation_ip"}

# Allowed values for stp (settlement type) — per public spec examples.
STP_KNOWN = {"coin", "card"}

# Tolerances and limits.
DEFAULT_CLOCK_SKEW = 60         # seconds, applied to both iat (future) and exp (past)
DEFAULT_JTI_CACHE_SIZE = 2048   # LRU eviction threshold
DEFAULT_JWKS_TTL = 3600         # seconds — spec says JWKS is cacheable ~1 hour
DEFAULT_HTTP_TIMEOUT = 15       # seconds

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# In-memory caches (thread-safe)
# ---------------------------------------------------------------------------


class _JWKSCache:
    def __init__(self, ttl: int = DEFAULT_JWKS_TTL):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._store: dict[str, tuple[dict[str, Any], float]] = {}

    def get(self, issuer: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._store.get(issuer)
            if not entry:
                return None
            jwks, expires_at = entry
            if time.time() >= expires_at:
                self._store.pop(issuer, None)
                return None
            return jwks

    def put(self, issuer: str, jwks: dict[str, Any]) -> None:
        with self._lock:
            self._store[issuer] = (jwks, time.time() + self._ttl)


class _JTILRU:
    """Bounded LRU set of (issuer, jti) tuples for replay mitigation."""

    def __init__(self, maxsize: int = DEFAULT_JTI_CACHE_SIZE):
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._store: "OrderedDict[tuple[str, str], float]" = OrderedDict()

    def check_and_add(self, issuer: str, jti: str, exp: int) -> bool:
        """Return True if newly added, False if jti was already seen (replay)."""
        key = (issuer, jti)
        now = time.time()
        with self._lock:
            # Opportunistic eviction of expired entries.
            stale = [k for k, e in self._store.items() if e <= now]
            for k in stale:
                self._store.pop(k, None)

            if key in self._store:
                self._store.move_to_end(key)
                return False

            self._store[key] = float(exp)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)
            return True


_JWKS = _JWKSCache()
_SEEN_JTI = _JTILRU()


# ---------------------------------------------------------------------------
# Low-level HTTP / JOSE helpers
# ---------------------------------------------------------------------------


def _http_get_json(url: str, timeout: int = DEFAULT_HTTP_TIMEOUT) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Accept": "application/json,application/jwk-set+json;q=0.9,*/*;q=0.1",
            "User-Agent": "hermes-kya-spec-plugin/2.0",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read().decode(charset, errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _jwt_split(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format: expected header.payload.signature")
    try:
        header = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as err:  # pragma: no cover - exercised via tests
        raise ValueError(f"Invalid JWT encoding: {err}") from err
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("JWT header and payload must each be a JSON object")
    return header, payload


def _jwks_url_for_issuer(issuer: str) -> str:
    """Derive the JWKS URL from an issuer claim.

    The spec says JWKS lives at the issuer's ``/.well-known/jwks.json``
    suffix. The issuer claim should be a URL; we normalize trailing slashes.
    """
    if not isinstance(issuer, str) or not issuer:
        raise ValueError("Issuer must be a non-empty string")
    if not (issuer.startswith("https://") or issuer.startswith("http://")):
        raise ValueError(f"Issuer '{issuer}' must be an http(s) URL")
    return issuer.rstrip("/") + "/.well-known/jwks.json"


def _select_jwk(jwks: dict[str, Any], kid: str) -> dict[str, Any]:
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ValueError("JWKS document has no 'keys' array")
    for key in keys:
        if isinstance(key, dict) and key.get("kid") == kid:
            return key
    raise ValueError(f"No JWK matched header kid '{kid}'")


def _verify_signature(token: str, jwk: dict[str, Any], expected_alg: str) -> None:
    """Verify the JWT signature using pyjwt + cryptography.

    pyjwt is already a project dep (``pyjwt[crypto]``); using it avoids hand-
    rolling P1363 vs DER conversion, which is the classic foot-gun.
    """
    import jwt as pyjwt
    from jwt.algorithms import ECAlgorithm

    if expected_alg not in SUPPORTED_JWA:
        raise ValueError(f"Algorithm '{expected_alg}' is not in SUPPORTED_JWA {sorted(SUPPORTED_JWA)}")

    # Construct a public key object from the JWK and verify.
    try:
        public_key = ECAlgorithm.from_jwk(json.dumps(jwk))
    except Exception as err:
        raise ValueError(f"Unable to load JWK as EC public key: {err}") from err

    try:
        # We've already enforced shape; here we only need signature + algo.
        # Disable pyjwt's audience/expiry checks because we run our own
        # spec-aware checks (with configurable skew) downstream.
        pyjwt.decode(
            token,
            public_key,
            algorithms=[expected_alg],
            options={
                "verify_signature": True,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "verify_aud": False,
                "verify_iss": False,
                "require": [],
            },
        )
    except pyjwt.InvalidSignatureError as err:
        raise ValueError(f"JWT signature verification failed: {err}") from err
    except pyjwt.InvalidAlgorithmError as err:
        raise ValueError(f"JWT algorithm not accepted: {err}") from err
    except pyjwt.DecodeError as err:
        raise ValueError(f"JWT decode failed: {err}") from err


# ---------------------------------------------------------------------------
# Spec-aware claim validation
# ---------------------------------------------------------------------------


class ValidationReport:
    """Plain container; not a dataclass to remain robust under importlib loading."""

    __slots__ = ("ok", "token_type", "issuer", "kid", "signature_verified", "errors", "warnings")

    def __init__(self, token_type: str = "") -> None:
        self.ok: bool = False
        self.token_type: str = token_type
        self.issuer: str | None = None
        self.kid: str | None = None
        self.signature_verified: bool = False
        self.errors: list[str] = []
        self.warnings: list[str] = []


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified)


def _validate_timestamps(
    payload: dict[str, Any],
    errors: list[str],
    clock_skew: int,
) -> None:
    now = int(time.time())

    iat = payload.get("iat")
    if isinstance(iat, (int, float)) and not isinstance(iat, bool):
        if int(iat) > now + clock_skew:
            errors.append("Claim 'iat' is in the future beyond allowed clock skew.")
    else:
        errors.append("Claim 'iat' must be a numeric Unix timestamp.")

    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and not isinstance(exp, bool):
        if int(exp) <= now - clock_skew:
            errors.append("Claim 'exp' indicates the token is expired.")
    else:
        errors.append("Claim 'exp' must be a numeric Unix timestamp.")


def _validate_kya_subclaims(payload: dict[str, Any], errors: list[str]) -> None:
    # aid is required as a top-level object for KYA / KYA-PAY tokens.
    aid = payload.get("aid")
    if not isinstance(aid, dict):
        errors.append("Claim 'aid' must be an object.")
    else:
        for required in AID_REQUIRED:
            if required not in aid:
                errors.append(f"Claim 'aid.{required}' is required.")
        creation_ip = aid.get("creation_ip")
        if isinstance(creation_ip, str) and creation_ip and not _is_public_ip(creation_ip):
            errors.append("Claim 'aid.creation_ip' must be a public IPv4 or IPv6 address.")

    # hid is optional; when present, email is required.
    hid = payload.get("hid")
    if hid is not None:
        if not isinstance(hid, dict):
            errors.append("Claim 'hid' must be an object when present.")
        else:
            for required in HID_REQUIRED_WHEN_PRESENT:
                if required not in hid:
                    errors.append(f"Claim 'hid.{required}' is required when 'hid' is present.")

    # apd is optional; when present, id and name are required.
    apd = payload.get("apd")
    if apd is not None:
        if not isinstance(apd, dict):
            errors.append("Claim 'apd' must be an object when present.")
        else:
            for required in APD_REQUIRED_WHEN_PRESENT:
                if required not in apd:
                    errors.append(f"Claim 'apd.{required}' is required when 'apd' is present.")


def _validate_pay_subclaims(payload: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    stp = payload.get("stp")
    if stp is not None and stp not in STP_KNOWN:
        warnings.append(
            f"Claim 'stp'='{stp}' is not in the public spec's known set {sorted(STP_KNOWN)}."
        )
    sti = payload.get("sti")
    if sti is not None and not isinstance(sti, dict):
        errors.append("Claim 'sti' must be an object when present.")


def _validate_shape(
    token_type: str,
    header: dict[str, Any],
    payload: dict[str, Any],
    expected_audience: str | None,
    expected_environment: str | None,
    trusted_issuers: set[str] | None,
    clock_skew: int,
    enforce_audience: bool,
) -> ValidationReport:
    report = ValidationReport(token_type=token_type)
    errors = report.errors
    warnings = report.warnings

    # Header shape
    missing_header = sorted(k for k in GENERAL_REQUIRED_HEADER if k not in header)
    if missing_header:
        errors.append(f"Missing required header claim(s): {', '.join(missing_header)}")

    alg = header.get("alg")
    if isinstance(alg, str) and alg and alg not in SUPPORTED_JWA:
        errors.append(
            f"Unsupported JWT algorithm '{alg}'. Expected one of: {sorted(SUPPORTED_JWA)}"
        )

    typ = header.get("typ")
    if isinstance(typ, str) and typ and typ not in TYP_ALLOWED:
        errors.append(f"Header 'typ' must be one of {sorted(TYP_ALLOWED)}, got '{typ}'")

    expected_typ = {"kya": "kya+jwt", "pay": "pay+jwt", "kya-pay": "kya-pay+jwt"}[token_type]
    if isinstance(typ, str) and typ and typ != expected_typ:
        errors.append(f"token_type='{token_type}' requires header typ='{expected_typ}', got '{typ}'")

    # Payload shape
    missing_payload = sorted(k for k in GENERAL_REQUIRED_PAYLOAD if k not in payload)
    if missing_payload:
        errors.append(f"Missing required payload claim(s): {', '.join(missing_payload)}")

    # jti must be a UUID string per spec.
    jti = payload.get("jti")
    if jti is not None:
        if not isinstance(jti, str) or not UUID_RE.match(jti):
            errors.append("Claim 'jti' must be a UUID string.")

    # iss must be a URL (we'll need it for JWKS lookup downstream).
    iss = payload.get("iss")
    if iss is not None and not (isinstance(iss, str) and (iss.startswith("https://") or iss.startswith("http://"))):
        errors.append("Claim 'iss' must be an http(s) URL.")
    report.issuer = iss if isinstance(iss, str) else None

    if trusted_issuers is not None and isinstance(iss, str) and iss not in trusted_issuers:
        errors.append(f"Issuer '{iss}' is not in the trusted-issuer allowlist.")

    # aud — REQUIRED to match expected when configured (spec: MUST validate).
    aud = payload.get("aud")
    if expected_audience is not None:
        if aud != expected_audience:
            errors.append(
                f"Claim 'aud'='{aud}' does not match expected_audience='{expected_audience}'."
            )
    elif enforce_audience:
        errors.append(
            "expected_audience was not provided; per the spec, recipients MUST validate 'aud'. "
            "Pass expected_audience or set enforce_audience=false explicitly to disable."
        )

    # env — spec validation guideline: MUST validate when an expected value is configured.
    if expected_environment is not None:
        if payload.get("env") != expected_environment:
            errors.append(
                f"Claim 'env'='{payload.get('env')}' does not match expected_environment='{expected_environment}'."
            )

    _validate_timestamps(payload, errors, clock_skew)

    if token_type in ("kya", "kya-pay"):
        _validate_kya_subclaims(payload, errors)
    if token_type in ("pay", "kya-pay"):
        _validate_pay_subclaims(payload, errors, warnings)

    report.kid = header.get("kid") if isinstance(header.get("kid"), str) else None
    report.ok = not errors
    return report


# ---------------------------------------------------------------------------
# End-to-end verification
# ---------------------------------------------------------------------------


def _verify_token(
    token_type: str,
    token: str,
    expected_audience: str | None,
    expected_environment: str | None,
    trusted_issuers: set[str] | None,
    clock_skew: int,
    enforce_audience: bool,
    enforce_replay_protection: bool,
    jwks_override: dict[str, Any] | None = None,
) -> ValidationReport:
    """Verify a KYA/PAY/KYA-PAY JWT end-to-end.

    Validation order:
        1. Decode header + payload (no signature trust yet).
        2. Run claim-shape validation. Collect, do not short-circuit.
        3. If shape is OK and ``iss``/``kid``/``alg`` are usable, fetch JWKS
           and verify the signature.
        4. Run replay-cache check on ``jti``.

    Always returns a :class:`ValidationReport`; raises only on programmer
    errors (e.g. bad token_type).
    """
    header, payload = _jwt_split(token)

    report = _validate_shape(
        token_type=token_type,
        header=header,
        payload=payload,
        expected_audience=expected_audience,
        expected_environment=expected_environment,
        trusted_issuers=trusted_issuers,
        clock_skew=clock_skew,
        enforce_audience=enforce_audience,
    )

    issuer = payload.get("iss")
    kid = header.get("kid")
    alg = header.get("alg")

    # Only attempt signature verification when we have enough to do so.
    can_verify = (
        isinstance(issuer, str)
        and isinstance(kid, str)
        and isinstance(alg, str)
        and alg in SUPPORTED_JWA
    )
    if can_verify:
        try:
            if jwks_override is not None:
                jwks = jwks_override
            else:
                jwks = _JWKS.get(issuer)
                if jwks is None:
                    jwks = _http_get_json(_jwks_url_for_issuer(issuer))
                    _JWKS.put(issuer, jwks)
            jwk = _select_jwk(jwks, kid)
            _verify_signature(token, jwk, alg)
            report.signature_verified = True
        except Exception as err:
            report.errors.append(f"Signature verification failed: {err}")
            report.signature_verified = False
    else:
        report.errors.append(
            "Cannot verify signature: missing or invalid iss/kid/alg in token."
        )

    # Replay protection (only useful once signature has been verified;
    # otherwise an attacker could pre-pollute the cache with arbitrary jti).
    if enforce_replay_protection and report.signature_verified:
        jti = payload.get("jti")
        exp = payload.get("exp")
        if isinstance(jti, str) and isinstance(exp, (int, float)):
            if not _SEEN_JTI.check_and_add(str(issuer), jti, int(exp)):
                report.errors.append(f"Replay detected: jti='{jti}' for issuer '{issuer}' was already seen.")

    report.ok = report.signature_verified and not report.errors
    return report


# ---------------------------------------------------------------------------
# Hermes plugin registration
# ---------------------------------------------------------------------------


def _coerce_trusted_issuers(value: Any) -> set[str] | None:
    """Build a trusted-issuer set from explicit param or env var.

    Env var ``TRUSTED_KYA_ISSUERS`` accepts a comma-separated list, mirroring
    ``TRUSTED_DIDS`` for parity with the existing A2A auth layer.
    """
    if value is None:
        env = os.environ.get("TRUSTED_KYA_ISSUERS", "")
        if not env.strip():
            return None
        return {item.strip() for item in env.split(",") if item.strip()}
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return set(items) if items else None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return set(items) if items else None
    raise ValueError("trusted_issuers must be a comma-separated string, list, or null")


def register(ctx):
    validate_schema = {
        "name": "kya_validate_claims",
        "description": (
            "Verify a KYA / PAY / KYA-PAY JWT issued under the KYAPay specification. "
            "Fetches the issuer's JWKS at {iss}/.well-known/jwks.json, matches the "
            "header kid, verifies the ES256 signature, and enforces spec-mandated "
            "claim shape, timestamps, audience binding, environment binding, and "
            "an optional trusted-issuer allowlist. Tracks jti in memory to "
            "mitigate replay. Returns a structured validation report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "token_type": {
                    "type": "string",
                    "enum": ["kya", "pay", "kya-pay"],
                    "description": "Token profile to validate against.",
                },
                "token": {
                    "type": "string",
                    "description": "Raw JWT string (header.payload.signature). Required.",
                },
                "expected_audience": {
                    "type": "string",
                    "description": (
                        "Audience value to enforce against payload.aud. Strongly "
                        "recommended — per the spec, recipients MUST validate aud. "
                        "If omitted, validation fails unless enforce_audience=false."
                    ),
                },
                "expected_environment": {
                    "type": "string",
                    "description": "Optional environment value to enforce against payload.env (e.g. 'production', 'sandbox').",
                },
                "trusted_issuers": {
                    "type": "string",
                    "description": (
                        "Comma-separated allowlist of issuer URLs to trust. "
                        "When omitted, falls back to the TRUSTED_KYA_ISSUERS env var. "
                        "When neither is set, any signature-verified issuer is accepted."
                    ),
                },
                "clock_skew_seconds": {
                    "type": "integer",
                    "description": f"Clock skew tolerance applied symmetrically to iat and exp. Defaults to {DEFAULT_CLOCK_SKEW}.",
                },
                "enforce_audience": {
                    "type": "boolean",
                    "description": "When true (default), missing expected_audience is an error. Set false only for diagnostic use.",
                },
                "enforce_replay_protection": {
                    "type": "boolean",
                    "description": "When true (default), reject tokens whose (iss, jti) has been seen before in this process.",
                },
            },
            "required": ["token_type", "token"],
        },
    }

    def validate_handler(params, **kwargs):
        params = params or {}
        token_type = str(params.get("token_type") or "").strip().lower()
        if token_type not in {"kya", "pay", "kya-pay"}:
            return json.dumps(
                {"error": "token_type must be one of: kya, pay, kya-pay"}, indent=2
            )

        token = str(params.get("token") or "").strip()
        if not token:
            return json.dumps({"error": "token is required"}, indent=2)

        try:
            trusted = _coerce_trusted_issuers(params.get("trusted_issuers"))
        except ValueError as err:
            return json.dumps({"error": str(err)}, indent=2)

        clock_skew_raw = params.get("clock_skew_seconds")
        if clock_skew_raw is None:
            clock_skew = DEFAULT_CLOCK_SKEW
        else:
            try:
                clock_skew = max(0, int(clock_skew_raw))
            except (TypeError, ValueError):
                return json.dumps(
                    {"error": "clock_skew_seconds must be an integer"}, indent=2
                )

        expected_audience = params.get("expected_audience")
        if expected_audience is not None:
            expected_audience = str(expected_audience)
        expected_environment = params.get("expected_environment")
        if expected_environment is not None:
            expected_environment = str(expected_environment)

        enforce_audience = bool(params.get("enforce_audience", True))
        enforce_replay = bool(params.get("enforce_replay_protection", True))

        try:
            report = _verify_token(
                token_type=token_type,
                token=token,
                expected_audience=expected_audience,
                expected_environment=expected_environment,
                trusted_issuers=trusted,
                clock_skew=clock_skew,
                enforce_audience=enforce_audience,
                enforce_replay_protection=enforce_replay,
            )
        except ValueError as err:
            return json.dumps({"error": str(err)}, indent=2)

        # Surface decoded claims for downstream policy decisions.
        try:
            header, payload = _jwt_split(token)
        except ValueError:
            header, payload = {}, {}

        return json.dumps(
            {
                "ok": report.ok,
                "token_type": report.token_type,
                "issuer": report.issuer,
                "kid": report.kid,
                "signature_verified": report.signature_verified,
                "header": header,
                "payload": payload,
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
        )

    ctx.register_tool(
        name="kya_validate_claims",
        toolset="kya-spec",
        schema=validate_schema,
        handler=validate_handler,
    )
