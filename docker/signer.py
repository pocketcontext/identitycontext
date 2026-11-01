#!/usr/bin/env python3
"""OCI HSM signing boundary. stdin/stdout protocol; fixed error messages only."""
import base64
import hashlib
import json
import os
import signal
import sys
import time

PREFIX = 'IDENTITYCONTEXT_'


def env(name):
    value = os.environ.get(PREFIX + name, '')
    if not value:
        raise ValueError('incomplete signing configuration')
    return value


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def integer(value):
    return b64(value.to_bytes((value.bit_length() + 7) // 8, 'big'))


def clients():
    import oci
    config = {'tenancy': env('OCI_TENANCY_ID'), 'user': env('OCI_USER_ID'),
              'fingerprint': env('OCI_FINGERPRINT'), 'region': env('OCI_REGION'),
              'key_content': env('OCI_PRIVATE_KEY')}
    kwargs = {'timeout': (5, 10), 'retry_strategy': oci.retry.NoneRetryStrategy()}
    from urllib.parse import urlsplit
    for key in ('KMS_CRYPTO_ENDPOINT', 'KMS_MANAGEMENT_ENDPOINT'):
        url = urlsplit(env(key))
        if url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.oraclecloud.com') or url.username or url.password or url.query or url.fragment:
            raise ValueError('invalid KMS endpoint')
    return (oci.key_management.KmsCryptoClient(config, service_endpoint=env('KMS_CRYPTO_ENDPOINT'), **kwargs),
            oci.key_management.KmsManagementClient(config, service_endpoint=env('KMS_MANAGEMENT_ENDPOINT'), **kwargs))


def jwks(management):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    versions = [env('KMS_KEY_VERSION_ID')]
    versions.extend(x for x in os.environ.get(PREFIX + 'KMS_PREVIOUS_KEY_VERSION_IDS', '').split(',') if x)
    if len(set(versions)) != len(versions) or len(versions) > 5:
        raise ValueError('invalid key versions')
    keys = []
    for version in versions:
        public = management.get_key_version(env('KMS_KEY_ID'), version).data.public_key
        key = load_pem_public_key(public.encode())
        if not isinstance(key, RSAPublicKey) or key.key_size < 3072:
            raise ValueError('invalid verification key')
        numbers = key.public_numbers()
        keys.append({'kty': 'RSA', 'use': 'sig', 'alg': 'RS256', 'kid': version,
                     'n': integer(numbers.n), 'e': integer(numbers.e)})
    return {'keys': keys}


def sign(claims, crypto):
    import oci
    expected = {'iss', 'sub', 'email', 'email_verified', 'hd', 'aud', 'iat', 'nbf', 'exp', 'jti'}
    if (not isinstance(claims, dict) or set(claims) != expected or claims['iss'] != 'https://id.pocketcontext.com'
            or claims['aud'] not in ('https://wiki.pocketcontext.com', 'https://notify.pocketcontext.com')
            or claims['email_verified'] is not True or claims['hd'] != 'pocketcontext.com'
            or not isinstance(claims['email'], str) or not claims['email'].endswith('@pocketcontext.com')
            or any(type(claims[k]) is not int for k in ('iat', 'nbf', 'exp'))
            or not 0 < claims['exp'] - claims['iat'] <= 60 or abs(time.time() - claims['iat']) > 10
            or claims['nbf'] != claims['iat']):
        raise ValueError('invalid signing payload')
    header = {'alg': 'RS256', 'typ': 'JWT', 'kid': env('KMS_KEY_VERSION_ID')}
    message = (b64(json.dumps(header, separators=(',', ':')).encode()) + '.' +
               b64(json.dumps(claims, separators=(',', ':')).encode())).encode()
    response = crypto.sign(oci.key_management.models.SignDataDetails(
        key_id=env('KMS_KEY_ID'), key_version_id=env('KMS_KEY_VERSION_ID'),
        signing_algorithm='SHA_256_RSA_PKCS1_V1_5', message_type='DIGEST',
        message=base64.b64encode(hashlib.sha256(message).digest()).decode())).data
    if response.key_version_id != env('KMS_KEY_VERSION_ID'):
        raise ValueError('unexpected signing key version')
    signature = base64.b64decode(response.signature, validate=True)
    if len(signature) != 384:
        raise ValueError('unexpected signature length')
    return message.decode() + '.' + b64(signature)


def main():
    def timeout(*_):
        raise TimeoutError()
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(20)
    try:
        crypto, management = clients()
        if sys.argv[1:] == ['jwks']:
            print(json.dumps(jwks(management)))
        elif sys.argv[1:] == ['sign']:
            data = sys.stdin.buffer.read(8193)
            if len(data) > 8192:
                raise ValueError()
            print(sign(json.loads(data), crypto))
        else:
            raise ValueError()
    except Exception:
        print('Identity signing operation failed.', file=sys.stderr)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
