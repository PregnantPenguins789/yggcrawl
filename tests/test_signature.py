"""Tests for Ed25519 signature verification with RFC 8785 canonicalization.

Tests signature parsing, record canonicalization, and verification logic
using generated test keys. RFC 8785 canonicalization is verified through
functional round-trip tests.
"""

import base64
import json
import pytest
from signature import (
    parse_public_key,
    parse_signature,
    canonicalize_record,
    verify_signature,
)


class TestPublicKeyParsing:
    """Test Ed25519 public key parsing from ed25519:base64 format."""

    def test_valid_public_key_parsing(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Create a valid public key string from a generated key
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        raw_key = public_key.public_bytes_raw()
        b64_key = base64.b64encode(raw_key).decode("utf-8")
        pubkey_str = f"ed25519:{b64_key}"

        pubkey = parse_public_key(pubkey_str)
        assert pubkey is not None

    def test_missing_prefix_returns_none(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Missing "ed25519:" prefix
        private_key = ed25519.Ed25519PrivateKey.generate()
        raw_key = private_key.public_key().public_bytes_raw()
        b64_key = base64.b64encode(raw_key).decode("utf-8")

        pubkey = parse_public_key(b64_key)  # No prefix
        assert pubkey is None

    def test_invalid_base64_returns_none(self):
        pubkey = parse_public_key("ed25519:not-valid-base64!@#$")
        assert pubkey is None

    def test_wrong_key_length_returns_none(self):
        # Ed25519 keys must be exactly 32 bytes
        short_key = base64.b64encode(b"short").decode("utf-8")
        pubkey = parse_public_key(f"ed25519:{short_key}")
        assert pubkey is None

    def test_none_input_returns_none(self):
        assert parse_public_key(None) is None
        assert parse_public_key("") is None
        assert parse_public_key(12345) is None


class TestSignatureParsing:
    """Test Ed25519 signature parsing from base64 format."""

    def test_valid_signature_parsing(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Create a signature by signing with a generated key
        private_key = ed25519.Ed25519PrivateKey.generate()
        sig_bytes = private_key.sign(b"test message")
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

        sig = parse_signature(sig_b64)
        assert sig is not None
        assert sig == sig_bytes

    def test_invalid_base64_returns_none(self):
        sig = parse_signature("not-valid-base64!@#$")
        assert sig is None

    def test_wrong_signature_length_returns_none(self):
        # Ed25519 signatures must be exactly 64 bytes
        short_sig = base64.b64encode(b"short").decode("utf-8")
        sig = parse_signature(short_sig)
        assert sig is None

    def test_none_input_returns_none(self):
        assert parse_signature(None) is None
        assert parse_signature("") is None


class TestCanonicalizeRecord:
    """Test RFC 8785 canonicalization with signature field removal."""

    def test_removes_signature_field(self):
        record = {
            "field1": "value1",
            "field2": 42,
            "signature": "should-be-removed",
        }

        canonical = canonicalize_record(record)
        assert canonical is not None

        # Verify signature field is not in canonical form
        canonical_str = canonical.decode("utf-8")
        assert "signature" not in canonical_str
        assert "should-be-removed" not in canonical_str

    def test_preserves_other_fields(self):
        record = {
            "version": 1,
            "operator_pubkey": "ed25519:abc",
            "service_type": "dictd",
            "signature": "not-included",
        }

        canonical = canonicalize_record(record)
        assert canonical is not None

        canonical_str = canonical.decode("utf-8")
        assert "version" in canonical_str
        assert "dictd" in canonical_str

    def test_sorts_keys_lexicographically(self):
        # RFC 8785 requires keys sorted lexicographically
        record1 = {"z": 1, "a": 2, "m": 3, "signature": "x"}
        record2 = {"a": 2, "m": 3, "z": 1, "signature": "x"}

        canonical1 = canonicalize_record(record1)
        canonical2 = canonicalize_record(record2)

        # Different input order should produce same canonical form
        assert canonical1 == canonical2

    def test_handles_nested_objects(self):
        record = {
            "endpoints": [
                {"network": "yggdrasil", "address": "[200:abcd::1]:8080"},
                {"network": "clearnet", "address": "example.com:8080"},
            ],
            "signature": "not-included",
        }

        canonical = canonicalize_record(record)
        assert canonical is not None
        # Should successfully canonicalize nested structures
        assert b"yggdrasil" in canonical

    def test_non_dict_returns_none(self):
        assert canonicalize_record(None) is None
        assert canonicalize_record("string") is None
        assert canonicalize_record([1, 2, 3]) is None


class TestSignatureVerification:
    """Test signature verification with functional tests."""

    def test_valid_signature_passes(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Generate a key and sign a message
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Create a record and sign it
        record = {
            "data": "test",
            "version": 1,
        }

        canonical = canonicalize_record(record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

        record["signature"] = sig_b64

        # Verify: should pass
        result = verify_signature(record, pubkey_str)
        assert result is True

    def test_invalid_signature_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Generate a key but use wrong signature
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Create a record with a wrong signature (all zeros)
        record = {
            "data": "test",
            "signature": base64.b64encode(b"\x00" * 64).decode("utf-8"),
        }

        result = verify_signature(record, pubkey_str)
        assert result is False

    def test_missing_signature_field_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Generate a key
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        record = {"data": "test"}  # No signature field

        result = verify_signature(record, pubkey_str)
        assert result is False

    def test_invalid_pubkey_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Generate a key and sign a message
        private_key = ed25519.Ed25519PrivateKey.generate()

        record = {
            "data": "test",
        }

        canonical = canonicalize_record(record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")

        record["signature"] = sig_b64

        # Try to verify with an invalid pubkey string
        result = verify_signature(record, "ed25519:invalid")
        assert result is False

    def test_non_dict_record_fails(self):
        result = verify_signature("not a dict", "ed25519:somepubkey")
        assert result is False

    def test_corrupted_message_fails(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        # Generate key and sign a message
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pubkey_raw = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(pubkey_raw).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Create a record with original data
        record = {
            "data": "original",
            "version": 1,
        }

        # Sign it
        canonical = canonicalize_record(record)
        sig_bytes = private_key.sign(canonical)
        sig_b64 = base64.b64encode(sig_bytes).decode("utf-8")
        record["signature"] = sig_b64

        # Verify it passes with original data
        result = verify_signature(record, pubkey_str)
        assert result is True

        # Now corrupt the message
        record["data"] = "modified"

        # Verification should fail
        result = verify_signature(record, pubkey_str)
        assert result is False


class TestSignatureRoundTrip:
    """Test end-to-end signature creation and verification.

    These tests use the cryptography library to sign and verify,
    confirming our parsing and canonicalization is correct.
    """

    def test_sign_and_verify_roundtrip(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        # Generate a test key pair
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        # Get the raw bytes
        public_bytes = public_key.public_bytes_raw()
        pubkey_b64 = base64.b64encode(public_bytes).decode("utf-8")
        pubkey_str = f"ed25519:{pubkey_b64}"

        # Create a test record
        record = {
            "version": 1,
            "operator_pubkey": pubkey_str,
            "service_type": "dictd",
            "endpoints": [{"network": "clearnet", "address": "example.com:2628"}],
        }

        # Canonicalize and sign
        canonical = canonicalize_record(record)
        assert canonical is not None

        signature = private_key.sign(canonical)
        sig_b64 = base64.b64encode(signature).decode("utf-8")

        # Add signature to record
        record["signature"] = sig_b64

        # Verify
        result = verify_signature(record, pubkey_str)
        assert result is True

    def test_verify_fails_with_wrong_key(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519

        # Generate two key pairs
        private_key1 = ed25519.Ed25519PrivateKey.generate()
        public_key1 = private_key1.public_key()

        private_key2 = ed25519.Ed25519PrivateKey.generate()
        public_key2 = private_key2.public_key()

        # Sign with key1
        public_bytes1 = public_key1.public_bytes_raw()
        pubkey_b64_1 = base64.b64encode(public_bytes1).decode("utf-8")
        pubkey_str_1 = f"ed25519:{pubkey_b64_1}"

        record = {"data": "test"}
        canonical = canonicalize_record(record)

        signature = private_key1.sign(canonical)
        sig_b64 = base64.b64encode(signature).decode("utf-8")
        record["signature"] = sig_b64

        # Try to verify with key2
        public_bytes2 = public_key2.public_bytes_raw()
        pubkey_b64_2 = base64.b64encode(public_bytes2).decode("utf-8")
        pubkey_str_2 = f"ed25519:{pubkey_b64_2}"

        result = verify_signature(record, pubkey_str_2)
        assert result is False
