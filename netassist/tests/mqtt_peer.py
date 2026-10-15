# -*- coding: utf-8 -*-
"""
MQTT 独立对端工具（可被 mqtt_e2e_test.py 调用，也可人工使用）。

用法示例：
  订阅：python mqtt_peer.py --host broker.emqx.io --port 1883 --topic 'test/+/x' \
            --mode sub --qos 1 --count 3 --timeout 15
  发布：python mqtt_peer.py --host broker.emqx.io --port 1883 --topic my/topic \
            --mode pub --payload '01 02 03' --format hex --qos 1 --count 2

退出码：0 表示达成预期（订阅收到预期条数 / 发布全部成功），否则非 0。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import time

import paho.mqtt.client as mqtt

ENC_MAP = {"utf-8": "utf-8", "utf8": "utf-8", "gbk": "gbk", "gb2312": "gbk"}


def encode_payload(payload: str, fmt: str, encoding: str) -> bytes:
    """按 format 将输入编码为实际字节（HEX 宽松解析：去空白、奇数左补 0、非法退回文本）"""
    if fmt == "hex":
        cleaned = "".join((payload or "").split())
        if cleaned and all(c in "0123456789abcdefABCDEF" for c in cleaned):
            if len(cleaned) % 2 != 0:
                cleaned = "0" + cleaned
            return bytes.fromhex(cleaned)
        # 解析不出合法 HEX 时退回文本编码
    enc = ENC_MAP.get(encoding, "utf-8")
    try:
        return (payload or "").encode(enc)
    except Exception:
        return (payload or "").encode("utf-8", errors="ignore")


def build_client(client_id: str):
    return mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )


def run_sub(args) -> int:
    state = {"connected": False, "messages": []}

    def on_connect(client, userdata, flags, reason_code, properties=None):
        state["connected"] = True
        client.subscribe(args.topic, args.qos)

    def on_message(client, userdata, msg):
        payload = bytes(msg.payload)
        state["messages"].append(
            {"topic": msg.topic, "hex": payload.hex(" ").upper(), "qos": msg.qos, "retain": bool(msg.retain)}
        )
        print(f"    <- topic={msg.topic} qos={msg.qos} retain={msg.retain} hex={payload.hex(' ').upper()}")

    client = build_client(args.client_id or f"peer-sub-{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, 30)
    client.loop_start()

    deadline = time.time() + args.timeout
    while time.time() < deadline and len(state["messages"]) < args.count:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    got = len(state["messages"])
    print(f"[sub] 收到 {got}/{args.count} 条（timeout={args.timeout}s）")
    return 0 if got >= args.count else 2


def run_pub(args) -> int:
    state = {"connected": False}
    payload = encode_payload(args.payload, args.format, args.encoding)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        state["connected"] = True

    client = build_client(args.client_id or f"peer-pub-{int(time.time())}")
    client.on_connect = on_connect
    client.connect(args.host, args.port, 30)
    client.loop_start()

    deadline = time.time() + 10
    while time.time() < deadline and not state["connected"]:
        time.sleep(0.05)

    if not state["connected"]:
        print("[pub] 连接 Broker 超时")
        client.loop_stop()
        return 3

    sent = 0
    for _ in range(max(1, args.count)):
        info = client.publish(args.topic, payload, args.qos, args.retain)
        if args.qos > 0 and info.rc == mqtt.MQTT_ERR_SUCCESS:
            info.wait_for_publish(timeout=5)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            sent += 1
        time.sleep(args.interval)

    time.sleep(0.3)
    client.loop_stop()
    client.disconnect()
    print(f"[pub] 已发布 {sent}/{args.count} 条 hex={payload.hex(' ').upper()} topic={args.topic} qos={args.qos} retain={args.retain}")
    return 0 if sent >= max(1, args.count) else 4


def main() -> int:
    ap = argparse.ArgumentParser(description="MQTT 独立对端（sub/pub）")
    ap.add_argument("--host", default="broker.emqx.io")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--mode", choices=["sub", "pub"], required=True)
    ap.add_argument("--payload", default="")
    ap.add_argument("--format", choices=["hex", "text"], default="text")
    ap.add_argument("--encoding", default="utf-8")
    ap.add_argument("--qos", type=int, default=0, choices=[0, 1, 2])
    ap.add_argument("--retain", action="store_true")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--client-id", default="")
    args = ap.parse_args()

    if args.mode == "sub":
        return run_sub(args)
    return run_pub(args)


if __name__ == "__main__":
    sys.exit(main())
