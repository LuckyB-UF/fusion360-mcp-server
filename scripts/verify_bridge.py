"""Direct end-to-end verification of the Fusion360 MCP add-in over the socket.
Speaks the same newline-delimited JSON protocol the MCP server uses.
"""
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9876


def send(sock, cmd_type, **params):
    payload = json.dumps({"type": cmd_type, "params": params}) + "\n"
    sock.sendall(payload.encode("utf-8"))
    buf = b""
    sock.settimeout(35.0)
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    line, _, _ = buf.partition(b"\n")
    resp = json.loads(line)
    if resp.get("status") == "error":
        raise RuntimeError(f"{cmd_type}: transport error: {resp.get('message')}")
    result = resp.get("result", {})
    if isinstance(result, dict) and result.get("ok") is False:
        raise RuntimeError(f"{cmd_type}: app error: {result.get('error_message')}\n"
                           f"hints={result.get('hints')}")
    return result


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect((HOST, PORT))
    out = {}

    out["1_ping"] = send(s, "ping")
    before = send(s, "get_scene_info")
    out["2_scene_before"] = {"bodies": before["bodies_count"],
                             "sketches": before["sketches_count"],
                             "design": before["design_name"]}

    out["3_create_sketch"] = send(s, "create_sketch", plane="xy")
    out["4_draw_rectangle"] = send(s, "draw_rectangle", width=5.0, height=3.0)
    out["5_extrude"] = send(s, "extrude", height=2.0, operation="new_body")

    after = send(s, "get_scene_info")
    out["6_scene_after"] = {"bodies": after["bodies_count"],
                            "sketches": after["sketches_count"],
                            "body_volumes_cm3": [round(b["volume"], 4)
                                                 for b in after["bodies"]]}
    s.close()

    print(json.dumps(out, indent=2))

    # Assertions
    new_bodies = after["bodies_count"] - before["bodies_count"]
    assert new_bodies == 1, f"expected +1 body, got {new_bodies}"
    newest_vol = after["bodies"][-1]["volume"]
    assert abs(newest_vol - 30.0) < 0.01, f"expected 30 cm3, got {newest_vol}"
    print("\nALL CHECKS PASSED: ping ok, sketch+rectangle+extrude -> 30 cm3 body.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"VERIFICATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
