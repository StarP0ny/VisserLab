"""Разведка шины: кто отвечает и что лежит в регистрах."""
import time

from .modbus import RtuClient, s16


def scan(port, bauds=(9600, 19200, 4800, 38400, 115200), max_addr=16):
    found = []
    for baud in bauds:
        print(f"--- {baud} бод ---")
        client = RtuClient(port, baud, timeout=0.15)
        for addr in range(1, max_addr + 1):
            regs = client.read_holding(addr, 0, 8)
            if regs is not None:
                print(f"  адрес {addr:3d}: ответ  regs[0..7] = {regs}")
                found.append((baud, addr))
            elif client.last_error and client.last_error.startswith("порт"):
                print(f"  {client.last_error}")
                return found
            time.sleep(0.03)
        client.close()
    if found:
        for baud, addr in found:
            print(f"НАЙДЕНО: адрес {addr} на {baud} бод")
    else:
        print("Никто не ответил. По порядку: питание 8–30 В (светодиод PWR); A<->B поменять "
              "местами; GND переходника <-> GND платы; DIP-адрес (все OFF обычно = 1); COM-порт.")
    return found


def dump(port, baud, addr, count=64, verbose=False):
    client = RtuClient(port, baud)
    print("рег   hex     u16      s16    /10      /100")
    for start in range(0, count, 8):
        regs = client.read_holding(addr, start, 8, verbose=verbose)
        if regs is None:
            print(f"{start:3d}..{start + 7:<3d} нет ответа ({client.last_error})")
            time.sleep(0.1)
            continue
        for i, w in enumerate(regs):
            v = s16(w)
            print(f"{start + i:3d}  0x{w:04X}  {w:6d}  {v:7d}  {v / 10:8.1f}  {v / 100:8.2f}")
        time.sleep(0.05)
    client.close()
