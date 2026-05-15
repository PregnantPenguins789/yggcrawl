"""Ed25519 signature verification with RFC 8785 canonical JSON.

Verifies records signed according to the Mesh Service Rendezvous Protocol.
All signatures are computed over the canonical JSON representation of the
record with the 'signature' field removed.
"""

import base64
import json
from typing import Optional

import rfc8785
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from logger import logger


def parse_public_key(pubkey_str: str) -> Optional[ed25519.Ed25519PublicKey]:
    """Parse Ed25519 public key from 'ed25519:base64' format.

    Args:
        pubkey_str: Public key in format 'ed25519:...' where ... is
                   base64-encoded (RFC 4648) 32-byte raw key.

    Returns:
        ed25519.Ed25519PublicKey or None if parsing fails.
    """
    if not pubkey_str or not isinstance(pubkey_str, str):
        return None

    if not pubkey_str.startswith("ed25519:"):
        logger.warning(f"Public key missing 'ed25519:' prefix: {pubkey_str[:20]}...")
        return None

    try:
        b64_key = pubkey_str[len("ed25519:"):]
        raw_key = base64.b64decode(b64_key)

        if len(raw_key) != 32:
            logger.warning(f"Ed25519 key must be 32 bytes, got {len(raw_key)}")
            return None

        return ed25519.Ed25519PublicKey.from_public_bytes(raw_key)
    except Exception as e:
        logger.warning(f"Failed to parse public key: {e}")
        return None


def parse_signature(sig_str: str) -> Optional[bytes]:
    """Parse Ed25519 signature from base64 format (RFC 4648).

    Args:
        sig_str: Base64-encoded signature (64-byte raw signature).

    Returns:
        Raw 64-byte signature bytes or None if parsing fails.
    """
    if not sig_str or not isinstance(sig_str, str):
        return None

    try:
        raw_sig = base64.b64decode(sig_str)
        if len(raw_sig) != 64:
            logger.warning(f"Ed25519 signature must be 64 bytes, got {len(raw_sig)}")
            return None
        return raw_sig
    except Exception as e:
        logger.warning(f"Failed to parse signature: {e}")
        return None


def canonicalize_record(record: dict) -> Optional[bytes]:
    """Canonicalize record to bytes for signature verification.

    Removes the 'signature' field and canonicalizes to RFC 8785 JSON form.

    Args:
        record: Dict representation of the record (with 'signature' field).

    Returns:
        Canonical JSON bytes or None if canonicalization fails.
    """
    if not isinstance(record, dict):
        return None

    try:
        # Create a copy without the signature field
        to_sign = {k: v for k, v in record.items() if k != "signature"}

        # RFC 8785 canonical JSON serialization (returns bytes)
        canonical_json = rfc8785.dumps(to_sign)
        return canonical_json

    except Exception as e:
        logger.warning(f"Failed to canonicalize record: {e}")
        return None


def verify_signature(record: dict, pubkey_str: str) -> bool:
    """Verify Ed25519 signature on a record.

    Args:
        record: Dict with 'signature' field containing the signature.
        pubkey_str: Public key in 'ed25519:base64' format.

    Returns:
        True if signature is valid, False otherwise.
        Always returns False on error (missing fields, parse errors, etc.).
    """
    if not isinstance(record, dict):
        logger.warning("Record must be a dict")
        return False

    # Extract signature from record
    sig_str = record.get("signature")
    if not sig_str:
        logger.warning("Record missing 'signature' field")
        return False

    # Parse public key
    pubkey = parse_public_key(pubkey_str)
    if pubkey is None:
        return False

    # Parse signature
    signature = parse_signature(sig_str)
    if signature is None:
        return False

    # Canonicalize record (without signature field)
    canonical = canonicalize_record(record)
    if canonical is None:
        return False

    # Verify signature
    try:
        pubkey.verify(signature, canonical)
        return True
    except InvalidSignature:
        logger.debug(f"Signature verification failed for pubkey {pubkey_str[:20]}...")
        return False
    except Exception as e:
        logger.warning(f"Signature verification error: {e}")
        return False
