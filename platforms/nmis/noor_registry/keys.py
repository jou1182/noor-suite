"""Generate the home signing key pair outside the repository."""
from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate(out_dir):
    root = Path(__file__).resolve().parents[3]
    out = Path(out_dir)
    if not out.is_absolute() or out.resolve().is_relative_to(root):
        raise ValueError('out-dir must be an absolute directory outside the repository')
    out.mkdir(parents=True, exist_ok=True)
    private_path = out / 'home_signing.pem'
    public_path = out / 'home_public.pem'
    if private_path.exists() or public_path.exists():
        raise FileExistsError('refusing to overwrite an existing key file')
    private = Ed25519PrivateKey.generate()
    private_path.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                                   serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    public_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM,
                                                               serialization.PublicFormat.SubjectPublicKeyInfo))
    private_path.chmod(0o600)
    return private_path, public_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('generate', choices=['generate'])
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    generate(args.out_dir)


if __name__ == '__main__':
    main()
