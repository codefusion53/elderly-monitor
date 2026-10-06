"""
Phase 4 - native Tuya Pulsar connection test.

Uses Tuya's current Python Pulsar SDK approach instead of
tuya-connector-python's old WebSocket consumer.

Reads:
    TUYA_ACCESS_ID
    TUYA_ACCESS_SECRET
    TUYA_REGION

from collector.config.

Run:
    python -m collector.pulsar_native_test
"""

from __future__ import annotations

import json
import logging
import sys

import pulsar
from Crypto.Cipher import AES

from . import config


log = logging.getLogger("pulsar_native_test")


PULSAR_ENDPOINTS = {
    "eu": "pulsar+ssl://mqe.tuyaeu.com:7285/",
    "us": "pulsar+ssl://mqe.tuyaus.com:7285/",
    "cn": "pulsar+ssl://mqe.tuyacn.com:7285/",
    "in": "pulsar+ssl://mqe.tuyain.com:7285/",
}

MQ_ENV = "event"


def get_authentication(access_id: str, access_secret: str):
    """
    Tuya's authentication scheme for the Pulsar client.
    """
    import hashlib

    md5_access_key = hashlib.md5(
        access_secret.encode("utf-8")
    ).hexdigest()

    combined = access_id + md5_access_key

    md5_combined = hashlib.md5(
        combined.encode("utf-8")
    ).hexdigest()

    password = '"' + md5_combined[8:24] + '"}'

    user_name = '{{"username": "{}","password"'.format(access_id)

    return pulsar.AuthenticationBasic(
        user_name,
        password,
        "auth1",
    )


def decrypt_message(pulsar_message, access_secret: str) -> str:
    """
    Decrypt a Tuya Pulsar message.

    Tuya's current Python Pulsar SDK selects the encryption
    method from the Pulsar message property 'em'.
    """
    payload = pulsar_message.data().decode("utf-8")

    decrypt_model = pulsar_message.properties().get("em")

    if decrypt_model:
        log.debug("Encryption model: %s", decrypt_model)
    else:
        log.debug("No encryption model property found; using ECB fallback")

    return decrypt_payload(
        payload,
        decrypt_model,
        access_secret,
    )


def decrypt_payload(
    payload: str,
    decrypt_model: str | None,
    access_secret: str,
) -> str:
    data_json = json.loads(payload)

    encrypted_data = data_json["data"]

    raw_bytes = __import__("base64").b64decode(encrypted_data)

    # Tuya derives the AES-128 key from bytes 8..23 of the Access Secret.
    key_bytes = access_secret[8:24].encode("utf-8")

    if decrypt_model == "aes_gcm":
        return decrypt_gcm(raw_bytes, key_bytes)

    return decrypt_ecb(raw_bytes, key_bytes)


def decrypt_gcm(raw_bytes: bytes, key_bytes: bytes) -> str:
    """
    AES-GCM format used by Tuya's current Pulsar SDK:

        first 12 bytes  = nonce
        final 16 bytes  = authentication tag
        middle          = ciphertext
    """
    nonce = raw_bytes[:12]
    ciphertext = raw_bytes[12:-16]
    auth_tag = raw_bytes[-16:]

    cipher = AES.new(
        key_bytes,
        AES.MODE_GCM,
        nonce=nonce,
    )

    plaintext = cipher.decrypt_and_verify(
        ciphertext,
        auth_tag,
    )

    return plaintext.decode("utf-8")


def decrypt_ecb(raw_bytes: bytes, key_bytes: bytes) -> str:
    cipher = AES.new(
        key_bytes,
        AES.MODE_ECB,
    )

    plaintext = cipher.decrypt(raw_bytes)

    return (
        plaintext
        .decode("utf-8")
        .replace("\r", "")
        .replace("\n", "")
        .replace("\f", "")
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    region = config.TUYA_REGION.split("-")[0].lower()

    endpoint = PULSAR_ENDPOINTS.get(region)

    if not endpoint:
        log.error(
            "Unsupported Tuya region: %s",
            config.TUYA_REGION,
        )
        sys.exit(1)

    log.info(
        "Connecting to Tuya Pulsar: %s",
        endpoint,
    )

    log.info(
        "Subscribing to Production topic: %s/out/%s",
        config.TUYA_ACCESS_ID,
        MQ_ENV,
    )

    client = pulsar.Client(
        endpoint,
        authentication=get_authentication(
            config.TUYA_ACCESS_ID,
            config.TUYA_ACCESS_SECRET,
        ),
        tls_allow_insecure_connection=True,
    )

    consumer = client.subscribe(
        f"{config.TUYA_ACCESS_ID}/out/{MQ_ENV}",
        f"{config.TUYA_ACCESS_ID}-sub",
        consumer_type=pulsar.ConsumerType.Failover,
    )

    log.info(
        "Connected. Waiting for Tuya events..."
    )

    try:
        while True:
            message = consumer.receive()

            # log.info(">>> PULSAR MESSAGE RECEIVED <<<")
            # log.info("PULSAR MESSAGE PROPERTIES: %s", message.properties())
            # log.info("PULSAR MESSAGE ID: %s", message.message_id())
            # log.info("PULSAR PAYLOAD SIZE: %d", len(message.data()))

            try:
                log.info(
                    "\nEncrypted Tuya message received."
                )

                log.debug(
                    "Pulsar properties: %s",
                    message.properties(),
                )

                decrypted = decrypt_message(
                    message,
                    config.TUYA_ACCESS_SECRET,
                )

                log.info(
                    "DECRYPTED EVENT: %s",
                    decrypted,
                )

                try:
                    data = json.loads(decrypted)

                    inner = data.get("data", data)

                    if isinstance(inner, dict):
                        log.info(
                            "  devId=%s",
                            inner.get("devId"),
                        )
                        log.info(
                            "  status=%s",
                            inner.get("status"),
                        )

                except json.JSONDecodeError:
                    log.warning(
                        "Decrypted payload was not JSON."
                    )

                consumer.acknowledge_cumulative(message)

            except Exception:
                log.exception(
                    "Failed to process Tuya message."
                )

                # Do not acknowledge failed messages.
                # Pulsar can redeliver them.

    except KeyboardInterrupt:
        log.info("Stopping...")

    finally:
        consumer.close()
        client.close()
        log.info("Stopped.")


if __name__ == "__main__":
    main()