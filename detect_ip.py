r"""检测本机局域网 IPv4 地址，供启动脚本调用。
用法: python detect_ip.py
输出到屏幕和 %TEMP%\lan_ip_display.txt
"""
import os
import socket
import subprocess
import sys


def get_lan_ips():
    ips = []
    # 方法1：通过 ipconfig 获取（设置超时防止卡死）
    try:
        output = subprocess.check_output(
            "ipconfig", shell=True, text=True,
            encoding="gbk", errors="replace",
            timeout=10  # 10秒超时，防止卡死
        )
        for line in output.splitlines():
            if "IPv4" in line or "IPv4 地址" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    ip = parts[-1].strip()
                    if _is_lan_ip(ip):
                        ips.append(ip)
    except subprocess.TimeoutExpired:
        print("[警告] ipconfig 命令超时，尝试备用方式...", file=sys.stderr)
    except Exception as e:
        print(f"[警告] ipconfig 获取失败: {e}，尝试备用方式...", file=sys.stderr)

    # 方法2：通过 socket 获取（备用）
    if not ips:
        try:
            socket.setdefaulttimeout(3)  # 3秒超时
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if _is_lan_ip(ip) and ip not in ips:
                    ips.append(ip)
        except Exception as e:
            print(f"[警告] socket 获取失败: {e}", file=sys.stderr)

    return ips


def _is_lan_ip(ip):
    if not ip:
        return False
    if ip.startswith("127."):
        return False
    if ip.startswith("169.254."):
        return False
    if ip.startswith("0."):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


if __name__ == "__main__":
    print("[检测] 正在识别本机局域网 IP...")
    ips = get_lan_ips()
    out_path = os.path.join(os.environ.get("TEMP", "."), "lan_ip_display.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        if not ips:
            print("[无法自动检测 IP]", file=f)
            print("请手动查看：打开 cmd 输入 ipconfig 找到 IPv4 地址", file=f)
            print("LAN_IPS=", file=f)
        else:
            for i, ip in enumerate(ips, 1):
                print(f"    {i}. http://{ip}:8501", file=f)
            if len(ips) > 1:
                print("", file=f)
                print("[提示] 检测到多个 IP 地址，请选择与访问者在同一", file=f)
                print("       局域网的那个地址发给对方。", file=f)
            print(f"LAN_IPS={','.join(ips)}", file=f)

    # 同时输出到屏幕
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.startswith("LAN_IPS="):
                print(line)
            else:
                # 输出供 batch 捕获（保留此行）
                print(line)
