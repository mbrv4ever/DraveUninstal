# -*- coding: utf-8 -*-
"""DraveUninstall - complete uninstaller (Dravenlock).

Verwijdert geinstalleerde programma's INCLUSIEF achtergebleven restmappen en
registersleutels die Windows laat staan. Maakt eerst een back-up (gezipte
restmappen + ge-exporteerde .reg-bestanden) zodat herstel mogelijk is.

Lokaal en offline. Windows-app: het lezen/wijzigen van het register en het
draaien van uninstallers werkt alleen op Windows. Op andere systemen draait de
app in demonstratiestand met voorbeelddata, zodat de interface te bekijken is.
"""
import os
import sys
import re
import json
import zipfile
import shutil
import tempfile
import datetime
import subprocess
import traceback

try:
    import winreg
    HEEFT_REGISTER = True
except Exception:
    winreg = None
    HEEFT_REGISTER = False

APP_NAAM = "DraveUninstall"
APP_VERSIE = "0.3.1"
DONATIE_URL = "https://paypal.me/roger076"
CONTACT = "service@dravenlock.nl"

BASIS = os.path.dirname(os.path.abspath(__file__))
FOUT_BESTAND = os.path.join(BASIS, "app-fout.txt")
CONFIG_BESTAND = os.path.join(BASIS, "config.json")

# Geen consolevenster laten flitsen bij subprocessen (Windows).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---- huisstijl ----
BG = "#0e0e11"
PANEL = "#16161b"
PANEL2 = "#1c1c22"
TEXT = "#d4d4d4"
MUTED = "#8a8a94"
ACCENT = "#6fa3d6"
LINE = "#23232b"
WARN = "#d68a6f"


def _excepthook(soort, waarde, tb):
    try:
        with open(FOUT_BESTAND, "w", encoding="utf-8") as f:
            f.write("DraveUninstall startfout\n\n")
            f.write("".join(traceback.format_exception(soort, waarde, tb)))
    except Exception:
        pass
    sys.__excepthook__(soort, waarde, tb)


sys.excepthook = _excepthook


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STANDAARD_CONFIG = {
    "taal": "auto",
    "backup_map": "",
    "toon_welkom": True,
}


def laad_config():
    cfg = dict(STANDAARD_CONFIG)
    try:
        with open(CONFIG_BESTAND, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def bewaar_config(cfg):
    try:
        tmp = CONFIG_BESTAND + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_BESTAND)
    except Exception:
        pass


def mensvriendelijke_grootte(n):
    n = float(n or 0)
    for eenheid in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or eenheid == "TB":
            if eenheid == "B":
                return "%d B" % int(n)
            return "%.1f %s" % (n, eenheid)
        n /= 1024.0
    return "%.1f TB" % n


def normaliseer(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def map_grootte(p):
    """Som van bestandsgroottes in een map (bytes). Veilig bij fouten."""
    totaal = 0
    if not p or not os.path.isdir(p):
        return 0
    for wortel, _mappen, best in os.walk(p):
        for f in best:
            try:
                totaal += os.path.getsize(os.path.join(wortel, f))
            except OSError:
                pass
    return totaal


def datum_opmaak(rauw):
    """InstallDate 'YYYYMMDD' -> 'DD-MM-YYYY'; anders de ruwe waarde of leeg."""
    s = str(rauw or "").strip()
    if re.fullmatch(r"\d{8}", s):
        return "%s-%s-%s" % (s[6:8], s[4:6], s[0:4])
    return s


def datum_sorteer(rauw):
    """Sorteerbare sleutel (YYYYMMDD als getal) voor de datumkolom."""
    s = str(rauw or "").strip()
    if re.fullmatch(r"\d{8}", s):
        try:
            return int(s)
        except ValueError:
            return 0
    return 0


def _foutreden(e):
    reden = type(e).__name__
    win = getattr(e, "winerror", None)
    if win:
        reden += " (WinError %s)" % win
    elif getattr(e, "errno", None):
        reden += " (errno %s)" % e.errno
    boodschap = getattr(e, "strerror", None) or str(e)
    if boodschap and boodschap not in reden:
        reden += ": " + boodschap
    return reden


# ---------------------------------------------------------------------------
# Geinstalleerde programma's lezen (register) - met demo-terugval
# ---------------------------------------------------------------------------
if HEEFT_REGISTER:
    UNINSTALL_LOCATIES = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "64-bit"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
         "32-bit"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "gebruiker"),
    ]
else:
    UNINSTALL_LOCATIES = []

# Voorbeeldprogramma's voor de demonstratiestand (niet-Windows).
DEMO_PROGRAMMAS = [
    {"naam": "Voorbeeld Foto Editor", "uitgever": "PixelWorks",
     "versie": "3.2.1", "grootte_bytes": 268 * 1024 * 1024,
     "datum": "20250114",
     "installatielocatie": r"C:\Program Files\PixelWorks\Foto Editor",
     "uninstall_string": r'"C:\Program Files\PixelWorks\Foto Editor\uninstall.exe"',
     "quiet": "", "bron": "64-bit", "hive": "HKLM",
     "sleutel_pad": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "sleutel_naam": "{A1B2C3D4-0001}"},
    {"naam": "SnelKlad Notities", "uitgever": "KladSoft",
     "versie": "1.0.7", "grootte_bytes": 42 * 1024 * 1024,
     "datum": "20240903",
     "installatielocatie": r"C:\Program Files (x86)\KladSoft\SnelKlad",
     "uninstall_string": r'"C:\Program Files (x86)\KladSoft\SnelKlad\unins000.exe"',
     "quiet": r'"C:\Program Files (x86)\KladSoft\SnelKlad\unins000.exe" /SILENT',
     "bron": "32-bit", "hive": "HKLM",
     "sleutel_pad": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
     "sleutel_naam": "SnelKlad_is1"},
    {"naam": "MediaSpeler Pro", "uitgever": "BlauwMedia",
     "versie": "12.4", "grootte_bytes": 130 * 1024 * 1024,
     "datum": "20251122",
     "installatielocatie": r"C:\Program Files\BlauwMedia\MediaSpeler",
     "uninstall_string": r'MsiExec.exe /X{11112222-3333-4444-5555-666677778888}',
     "quiet": r'MsiExec.exe /X{11112222-3333-4444-5555-666677778888} /quiet',
     "bron": "64-bit", "hive": "HKLM",
     "sleutel_pad": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "sleutel_naam": "{11112222-3333-4444-5555-666677778888}"},
    {"naam": "ToolBoxje", "uitgever": "HandigeTools",
     "versie": "0.9.3", "grootte_bytes": 18 * 1024 * 1024,
     "datum": "20230718",
     "installatielocatie": "",
     "uninstall_string": r'"C:\Users\Demo\AppData\Local\ToolBoxje\uninstall.exe"',
     "quiet": "", "bron": "gebruiker", "hive": "HKCU",
     "sleutel_pad": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
     "sleutel_naam": "ToolBoxje"},
]


def _reg_waarde(sleutel, naam):
    try:
        waarde, _ = winreg.QueryValueEx(sleutel, naam)
        return waarde
    except OSError:
        return None


def lees_programmas():
    """Lijst van geinstalleerde programma's (uit het register, of demo)."""
    if not HEEFT_REGISTER:
        return [dict(d) for d in DEMO_PROGRAMMAS]
    apps = []
    gezien = set()
    for hive, pad, bron in UNINSTALL_LOCATIES:
        try:
            hoofd = winreg.OpenKey(hive, pad)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    subnaam = winreg.EnumKey(hoofd, i)
                except OSError:
                    break
                i += 1
                try:
                    sub = winreg.OpenKey(hoofd, subnaam)
                except OSError:
                    continue
                try:
                    naam = _reg_waarde(sub, "DisplayName")
                    systeem = _reg_waarde(sub, "SystemComponent")
                    releasetype = _reg_waarde(sub, "ReleaseType")
                    ouder = _reg_waarde(sub, "ParentKeyName")
                    uninstall = _reg_waarde(sub, "UninstallString")
                    if not naam or systeem == 1 or not uninstall:
                        continue
                    if ouder or releasetype in ("Update", "Hotfix",
                                                "Security Update"):
                        continue
                    sleutel_id = (naam.lower(),
                                  str(_reg_waarde(sub, "DisplayVersion") or ""))
                    if sleutel_id in gezien:
                        continue
                    gezien.add(sleutel_id)
                    grootte = _reg_waarde(sub, "EstimatedSize")
                    apps.append({
                        "naam": naam,
                        "uitgever": _reg_waarde(sub, "Publisher") or "",
                        "versie": _reg_waarde(sub, "DisplayVersion") or "",
                        "grootte_bytes": int(grootte) * 1024 if grootte else 0,
                        "datum": _reg_waarde(sub, "InstallDate") or "",
                        "installatielocatie": _reg_waarde(sub, "InstallLocation") or "",
                        "uninstall_string": uninstall,
                        "quiet": _reg_waarde(sub, "QuietUninstallString") or "",
                        "bron": bron,
                        "hive": ("HKLM" if hive == winreg.HKEY_LOCAL_MACHINE
                                 else "HKCU"),
                        "sleutel_pad": pad,
                        "sleutel_naam": subnaam,
                    })
                finally:
                    winreg.CloseKey(sub)
        finally:
            winreg.CloseKey(hoofd)
    apps.sort(key=lambda a: a["naam"].lower())
    return apps


# ---------------------------------------------------------------------------
# Restanten opsporen (mappen + registersleutels)
# ---------------------------------------------------------------------------
# Mapnamen die we NOOIT als restant behandelen (te algemeen / kritiek).
BESCHERMDE_NAMEN = {
    "windows", "system32", "syswow64", "programfiles", "programfilesx86",
    "programdata", "users", "appdata", "local", "locallow", "roaming",
    "microsoft", "commonfiles", "temp", "tmp", "default", "public",
    "documents", "downloads", "desktop", "startmenu", "programs", "google",
}


def _hive_const(naam):
    if not HEEFT_REGISTER:
        return None
    return (winreg.HKEY_LOCAL_MACHINE if naam == "HKLM"
            else winreg.HKEY_CURRENT_USER)


def get_zoek_roots():
    roots = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                "LOCALAPPDATA", "APPDATA", "PROGRAMDATA"):
        v = os.environ.get(env)
        if v:
            roots.append(v)
    la = os.environ.get("LOCALAPPDATA")
    if la:
        roots.append(os.path.join(la, "Programs"))
    # dedup, alleen bestaande
    uniek = []
    for r in roots:
        r = os.path.normpath(r)
        if r not in uniek and os.path.isdir(r):
            uniek.append(r)
    return uniek


def _veilig_mappad(p):
    """Weiger kritieke mappen en mappen te dicht bij de schijfwortel."""
    pl = os.path.normpath(p)
    basis = normaliseer(os.path.basename(pl))
    if not basis or basis in BESCHERMDE_NAMEN:
        return False
    # minstens twee niveaus diep (drive + map + submap), bv C:\X\Y
    delen = [d for d in pl.replace("\\", "/").split("/") if d]
    if len(delen) < 3:
        return False
    return True


def zoek_rest_mappen(app, roots=None):
    """Restmappen die op naam of uitgever lijken (voorzichtig).
    Geeft een lijst van (pad, grootte_bytes)."""
    if roots is None:
        roots = get_zoek_roots()
    doelen = []
    namen = [n for n in (normaliseer(app.get("naam")),
                         normaliseer(app.get("uitgever"))) if len(n) >= 4]
    loc = (app.get("installatielocatie") or "").strip().rstrip("\\/")
    if loc and os.path.isdir(loc) and _veilig_mappad(loc):
        doelen.append(loc)
    for root in roots:
        try:
            inhoud = os.listdir(root)
        except OSError:
            continue
        for naam in inhoud:
            p = os.path.join(root, naam)
            if not os.path.isdir(p):
                continue
            nn = normaliseer(naam)
            if nn in BESCHERMDE_NAMEN or len(nn) < 3:
                continue
            if any(n in nn or nn in n for n in namen) and _veilig_mappad(p):
                doelen.append(p)
    uniek = []
    for d in doelen:
        d = os.path.normpath(d)
        if d not in uniek:
            uniek.append(d)
    return [(d, map_grootte(d)) for d in uniek]


REG_ZOEK = [("HKCU", r"SOFTWARE"),
            ("HKLM", r"SOFTWARE"),
            ("HKLM", r"SOFTWARE\WOW6432Node")]


def zoek_rest_sleutels(app, eigen=True):
    """Registersleutels die op naam of uitgever lijken (+ optioneel de eigen
    uninstall-sleutel)."""
    treffers = []
    if eigen and app.get("sleutel_naam"):
        treffers.append(app["hive"] + "\\" + app["sleutel_pad"] + "\\" +
                        app["sleutel_naam"])
    if not HEEFT_REGISTER:
        # demo: een paar plausibele sleutels
        u = app.get("uitgever") or app["naam"]
        treffers.append("HKCU\\SOFTWARE\\" + u)
        treffers.append("HKLM\\SOFTWARE\\" + u + "\\" + app["naam"])
        uniek = []
        for t in treffers:
            if t not in uniek:
                uniek.append(t)
        return uniek
    namen = [n for n in (normaliseer(app.get("naam")),
                         normaliseer(app.get("uitgever"))) if len(n) >= 4]
    for hive_naam, pad in REG_ZOEK:
        hive = _hive_const(hive_naam)
        try:
            key = winreg.OpenKey(hive, pad)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                sn = normaliseer(sub)
                if sn in BESCHERMDE_NAMEN or len(sn) < 4:
                    continue
                if any(n in sn or sn in n for n in namen):
                    treffers.append(hive_naam + "\\" + pad + "\\" + sub)
        finally:
            winreg.CloseKey(key)
    uniek = []
    for t in treffers:
        if t not in uniek:
            uniek.append(t)
    return uniek


# ---------------------------------------------------------------------------
# Back-up (restmappen zippen + registersleutels naar .reg exporteren)
# ---------------------------------------------------------------------------
def backup_map_pad(cfg):
    p = (cfg.get("backup_map") or "").strip()
    return p if p else os.path.join(BASIS, "DraveUninstall-backups")


def _exporteer_sleutel(volledige_naam, doelbestand):
    """Exporteer een registersleutel naar een .reg-bestand (Windows: reg export)."""
    if not HEEFT_REGISTER:
        # demo: schrijf een nep-.reg zodat de back-up toch iets bevat
        try:
            with open(doelbestand, "w", encoding="utf-16") as f:
                f.write("Windows Registry Editor Version 5.00\r\n\r\n")
                f.write("; (demo) export van %s\r\n" % volledige_naam)
            return True
        except Exception:
            return False
    try:
        r = subprocess.run(["reg", "export", volledige_naam, doelbestand, "/y"],
                           capture_output=True, timeout=30, creationflags=NO_WINDOW)
        return r.returncode == 0 and os.path.exists(doelbestand)
    except Exception:
        return False


def maak_backup(app, mappen, sleutels, doelmap):
    """Zip restmappen + ge-exporteerde .reg-bestanden met een manifest.
    Geeft (zip_pad, aantal_mappen, aantal_sleutels) of (None, 0, 0)."""
    os.makedirs(doelmap, exist_ok=True)
    stempel = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    veilige_naam = re.sub(r"[^A-Za-z0-9_-]", "_", app.get("naam", "app"))[:40]
    zip_pad = os.path.join(doelmap, "backup_%s_%s.zip" % (veilige_naam, stempel))
    manifest = {"app": app.get("naam", ""), "datum": stempel,
                "mappen": [], "sleutels": []}
    tmpdir = tempfile.mkdtemp(prefix="drvuninst_")
    reg_bestanden = []
    try:
        for idx, vol in enumerate(sleutels):
            regf = os.path.join(tmpdir, "sleutel_%d.reg" % idx)
            if _exporteer_sleutel(vol, regf):
                reg_bestanden.append((vol, regf))
        with zipfile.ZipFile(zip_pad, "w", zipfile.ZIP_DEFLATED) as z:
            for mi, m in enumerate(mappen):
                aantal = 0
                for wortel, _mappen, best in os.walk(m):
                    for f in best:
                        fp = os.path.join(wortel, f)
                        rel = os.path.relpath(fp, m).replace("\\", "/")
                        try:
                            z.write(fp, "map_%d/%s" % (mi, rel))
                            aantal += 1
                        except OSError:
                            pass
                manifest["mappen"].append(
                    {"id": "map_%d" % mi, "pad": os.path.abspath(m),
                     "bestanden": aantal})
            for ri, (vol, regf) in enumerate(reg_bestanden):
                z.write(regf, "reg/sleutel_%d.reg" % ri)
                manifest["sleutels"].append(
                    {"id": "reg/sleutel_%d.reg" % ri, "naam": vol})
            z.writestr("manifest.json",
                       json.dumps(manifest, ensure_ascii=False, indent=1))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return zip_pad, len(manifest["mappen"]), len(manifest["sleutels"])


def lees_backups(map_pad):
    uit = []
    if not os.path.isdir(map_pad):
        return uit
    for naam in os.listdir(map_pad):
        if not (naam.startswith("backup_") and naam.endswith(".zip")):
            continue
        vol = os.path.join(map_pad, naam)
        info = {"pad": vol, "naam": naam, "app": "", "datum": "",
                "mappen": 0, "sleutels": 0, "grootte": 0}
        try:
            info["grootte"] = os.path.getsize(vol)
            with zipfile.ZipFile(vol, "r") as z:
                m = json.loads(z.read("manifest.json").decode("utf-8"))
                info["app"] = m.get("app", "")
                info["datum"] = m.get("datum", "")
                info["mappen"] = len(m.get("mappen", []))
                info["sleutels"] = len(m.get("sleutels", []))
        except Exception:
            continue
        uit.append(info)
    uit.sort(key=lambda x: x["naam"], reverse=True)
    return uit


def zet_backup_terug(zip_pad):
    """Zet restmappen terug en importeer de .reg-bestanden weer.
    Geeft (mappen_terug, sleutels_terug, mislukt)."""
    mappen_terug = sleutels_terug = mislukt = 0
    tmpdir = tempfile.mkdtemp(prefix="drvuninst_herstel_")
    try:
        with zipfile.ZipFile(zip_pad, "r") as z:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            namen = z.namelist()
            # mappen terugzetten
            for item in manifest.get("mappen", []):
                arc_prefix = item["id"] + "/"
                doelmap = item["pad"]
                ok = True
                for naam in namen:
                    if not naam.startswith(arc_prefix):
                        continue
                    rel = naam[len(arc_prefix):]
                    if not rel:
                        continue
                    doel = os.path.join(doelmap, rel.replace("/", os.sep))
                    try:
                        os.makedirs(os.path.dirname(doel), exist_ok=True)
                        with z.open(naam) as bron, open(doel, "wb") as uit:
                            uit.write(bron.read())
                    except (OSError, PermissionError):
                        ok = False
                if ok:
                    mappen_terug += 1
                else:
                    mislukt += 1
            # registersleutels terug (reg import)
            for item in manifest.get("sleutels", []):
                try:
                    data = z.read(item["id"])
                    regf = os.path.join(tmpdir, os.path.basename(item["id"]))
                    with open(regf, "wb") as f:
                        f.write(data)
                    if HEEFT_REGISTER:
                        r = subprocess.run(["reg", "import", regf],
                                           capture_output=True, timeout=30,
                                           creationflags=NO_WINDOW)
                        if r.returncode == 0:
                            sleutels_terug += 1
                        else:
                            mislukt += 1
                    else:
                        sleutels_terug += 1
                except Exception:
                    mislukt += 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return mappen_terug, sleutels_terug, mislukt


# ---------------------------------------------------------------------------
# Verwijderen
# ---------------------------------------------------------------------------
def verwijder_map(p):
    """Verwijder een map en inhoud. Geeft (verwijderd, fouten[list (pad,reden)])."""
    verwijderd = 0
    fouten = []
    if not os.path.isdir(p):
        return verwijderd, fouten
    for wortel, mappen, best in os.walk(p, topdown=False):
        for f in best:
            fp = os.path.join(wortel, f)
            try:
                os.remove(fp)
                verwijderd += 1
            except (OSError, PermissionError) as e:
                fouten.append((fp, _foutreden(e)))
        for d in mappen:
            try:
                os.rmdir(os.path.join(wortel, d))
            except OSError:
                pass
    try:
        os.rmdir(p)
    except OSError as e:
        fouten.append((p, _foutreden(e)))
    return verwijderd, fouten


def _verwijder_sleutel_recursief(hive, pad):
    sleutel = winreg.OpenKey(hive, pad, 0, winreg.KEY_ALL_ACCESS)
    try:
        while True:
            try:
                sub = winreg.EnumKey(sleutel, 0)
            except OSError:
                break
            _verwijder_sleutel_recursief(hive, pad + "\\" + sub)
    finally:
        winreg.CloseKey(sleutel)
    winreg.DeleteKey(hive, pad)


def verwijder_sleutel(volledige_naam):
    """volledige_naam bv 'HKLM\\SOFTWARE\\X\\Y'. Geeft (ok, reden)."""
    if not HEEFT_REGISTER:
        return True, ""   # demo
    try:
        hive_naam, pad = volledige_naam.split("\\", 1)
        hive = _hive_const(hive_naam)
        _verwijder_sleutel_recursief(hive, pad)
        return True, ""
    except OSError as e:
        return False, _foutreden(e)


def draai_uninstaller(app, stil=False):
    """Start de eigen uninstaller van het programma. Geeft (gestart, reden)."""
    cmd = app.get("quiet") if (stil and app.get("quiet")) else app.get("uninstall_string")
    if not cmd:
        return False, "geen uninstall-opdracht"
    if not HEEFT_REGISTER:
        return True, "(demo) zou uitvoeren: " + cmd
    try:
        subprocess.Popen(cmd, shell=True)
        return True, ""
    except Exception as e:
        return False, _foutreden(e)


# ===========================================================================
# GUI
# ===========================================================================
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView, QLineEdit,
    QStatusBar, QMessageBox, QDialog, QTextBrowser, QComboBox, QFormLayout,
    QDialogButtonBox, QAbstractItemView, QListWidget, QCheckBox, QProgressBar,
)
from PyQt6.QtGui import (
    QAction, QIcon, QDesktopServices, QColor, QPixmap, QPalette,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QLocale, QSize, QTimer


def detecteer_taal():
    try:
        naam = QLocale.system().name().lower()
        return "nl" if naam.startswith("nl") else "en"
    except Exception:
        return "en"


TEKST = {
    "nl": {
        "ondertitel": "Complete uninstaller - lokaal en offline",
        "menu_inst": "Instellingen",
        "menu_help": "Help",
        "instellingen": "Instellingen",
        "sluiten": "Sluiten",
        "snelgids": "Snelgids",
        "welkom_menu": "Welkom / waarschuwing",
        "over": "Over DraveUninstall",
        "donatie": "Donatie",
        "vernieuwen": "Vernieuwen",
        "deinstalleren": "De-installeren...",
        "backups": "Back-ups...",
        "zoek": "Zoeken in programma's...",
        "kolom_naam": "Programma",
        "kolom_uitgever": "Uitgever",
        "kolom_versie": "Versie",
        "kolom_grootte": "Grootte",
        "kolom_bron": "Type",
        "bezig_lezen": "Programma's lezen...",
        "klaar_lezen": "{n} programma's gevonden.",
        "demo_strook": ("Demonstratiestand: dit is geen Windows, dus je ziet "
                        "voorbeelddata. Op Windows verschijnen je echte programma's."),
        "niets_geselecteerd": "Kies eerst een programma in de lijst.",
        "taal": "Taal",
        "taal_auto": "Automatisch (computertaal)",
        "opslaan": "Opslaan",
        "annuleren": "Annuleren",
        "sluit": "Sluiten",
        # de-installeren
        "deinst_titel": "Programma de-installeren",
        "deinst_intro": "Je staat op het punt dit programma te de-installeren:",
        "deinst_stap1": ("1) De ingebouwde uninstaller van het programma wordt "
                         "gestart. Doorloop die en wacht tot hij klaar is."),
        "deinst_stap2": ("2) Daarna zoekt DraveUninstall naar achtergebleven "
                         "restmappen en registersleutels, maakt er een back-up "
                         "van, en kan ze verwijderen."),
        "deinst_start": "Uninstaller starten",
        "deinst_gestart": ("De uninstaller is gestart. Voltooi hem en klik daarna "
                           "op 'Restanten zoeken'."),
        "deinst_demo": "(Demo) De uninstaller zou nu starten:\n{cmd}",
        "restanten_zoeken": "Restanten zoeken",
        "deinst_mislukt": "Kon de uninstaller niet starten: {reden}",
        # restanten
        "rest_titel": "Achtergebleven restanten",
        "rest_intro": ("Dit lijkt achtergebleven van '{app}'. Controleer het goed - "
                       "vink alleen aan wat je echt wilt verwijderen."),
        "rest_geen": "Geen restanten gevonden. Mooi opgeruimd!",
        "rest_mappen": "Restmappen",
        "rest_sleutels": "Registersleutels",
        "rest_backup_eerst": "Eerst een back-up maken (sterk aanbevolen)",
        "rest_verwijderen": "Geselecteerde verwijderen",
        "rest_waarschuwing": ("Let op: verwijderde mappen en registersleutels zijn "
                              "alleen via de back-up terug te halen. Controleer de "
                              "lijst zorgvuldig."),
        "rest_klaar": "Klaar: {mappen} mappen en {sleutels} sleutels verwijderd.",
        "rest_klaar_fout": ("Klaar: {mappen} mappen en {sleutels} sleutels "
                            "verwijderd, {fout} overgeslagen (zie logboek)."),
        "rest_backup_klaar": "Back-up gemaakt: {pad}",
        "bezig_verwijderen": "Verwijderen...",
        "deinst_bezig": "De uninstaller draait... wacht tot hij klaar is.",
        "bezig_zoeken": "Restanten zoeken...",
        "geforceerd": "Geforceerde opruiming...",
        "gef_titel": "Geforceerde opruiming",
        "gef_intro": ("Voor een programma dat je al (deels) verwijderd hebt. Typ de naam en eventueel de uitgever; DraveUninstall zoekt dan naar achtergebleven mappen en registersleutels."),
        "gef_naam": "Programmanaam",
        "gef_uitgever": "Uitgever (optioneel)",
        "gef_zoek": "Restanten zoeken",
        "gef_leeg": "Vul minstens een programmanaam van 3 tekens in.",
        "kolom_datum": "Geinstalleerd",
        "batch_klaar": "Klaar met {n} programma's.",
        # back-ups
        "terug_titel": "Back-ups (herstellen)",
        "terug_intro": ("Kies een back-up om terug te zetten. Restmappen worden "
                        "teruggeplaatst en de registersleutels opnieuw geimporteerd."),
        "terug_geen": "Nog geen back-ups.",
        "terug_item": "{app}  -  {datum}  -  {mappen} mappen, {sleutels} sleutels  -  {grootte}",
        "terugzetten": "Terugzetten",
        "terug_bevestig": "Deze back-up terugzetten (mappen + registersleutels)?",
        "terug_klaar": "Teruggezet: {mappen} mappen, {sleutels} sleutels.",
        "terug_klaar_fout": "Teruggezet: {mappen} mappen, {sleutels} sleutels, {fout} mislukt.",
        "map_openen": "Map openen",
        # welkom
        "welkom_titel": "Welkom bij DraveUninstall",
        "welkom_intro": ("DraveUninstall verwijdert geinstalleerde programma's "
                         "EN de rommel die Windows laat staan: restmappen en "
                         "registersleutels. Alles gebeurt lokaal."),
        "welkom_waarschuwing": ("Let op: dit programma wijzigt het Windows-register "
                                "en verwijdert mappen. Verkeerd gebruik kan andere "
                                "software beschadigen. DraveUninstall maakt daarom "
                                "altijd eerst een back-up, en jij bevestigt elke stap."),
        "welkom_stap1": "1. Kies een programma en de-installeer het.",
        "welkom_stap2": "2. Bekijk de gevonden restanten goed voor je iets verwijdert.",
        "welkom_stap3": "3. Laat de back-up aan staan, zodat je altijd terug kunt.",
        "welkom_veilig": ("Veilig? Ja - lokaal en offline. Je antivirus kan een "
                          "uninstaller toch even waarschuwen (vals alarm); zie de "
                          "Snelgids."),
        "welkom_niet_meer": "Dit venster niet meer tonen bij opstarten",
        "welkom_start": "Aan de slag",
        "over_tekst": ("DraveUninstall - complete uninstaller in de Dravenlock-"
                       "huisstijl. Lokaal, offline, toegankelijk, donationware.\n\n"
                       "Versie {versie}\nContact: {contact}\nDonatie: {donatie}"),
    },
    "en": {
        "ondertitel": "Complete uninstaller - local and offline",
        "menu_inst": "Settings",
        "menu_help": "Help",
        "instellingen": "Settings",
        "sluiten": "Close",
        "snelgids": "Quick guide",
        "welkom_menu": "Welcome / warning",
        "over": "About DraveUninstall",
        "donatie": "Donate",
        "vernieuwen": "Refresh",
        "deinstalleren": "Uninstall...",
        "backups": "Backups...",
        "zoek": "Search programs...",
        "kolom_naam": "Program",
        "kolom_uitgever": "Publisher",
        "kolom_versie": "Version",
        "kolom_grootte": "Size",
        "kolom_bron": "Type",
        "bezig_lezen": "Reading programs...",
        "klaar_lezen": "{n} programs found.",
        "demo_strook": ("Demo mode: this is not Windows, so you see sample data. "
                        "On Windows your real programs appear."),
        "niets_geselecteerd": "Select a program in the list first.",
        "taal": "Language",
        "taal_auto": "Automatic (system language)",
        "opslaan": "Save",
        "annuleren": "Cancel",
        "sluit": "Close",
        "deinst_titel": "Uninstall program",
        "deinst_intro": "You are about to uninstall this program:",
        "deinst_stap1": ("1) The program's own uninstaller starts. Go through it "
                         "and wait until it finishes."),
        "deinst_stap2": ("2) Then DraveUninstall looks for leftover folders and "
                         "registry keys, backs them up, and can remove them."),
        "deinst_start": "Start uninstaller",
        "deinst_gestart": ("The uninstaller started. Finish it, then click 'Find "
                           "leftovers'."),
        "deinst_demo": "(Demo) The uninstaller would start now:\n{cmd}",
        "restanten_zoeken": "Find leftovers",
        "deinst_mislukt": "Could not start the uninstaller: {reden}",
        "rest_titel": "Leftovers",
        "rest_intro": ("This looks left behind by '{app}'. Check carefully - tick "
                       "only what you really want to remove."),
        "rest_geen": "No leftovers found. Nice and clean!",
        "rest_mappen": "Leftover folders",
        "rest_sleutels": "Registry keys",
        "rest_backup_eerst": "Make a backup first (strongly recommended)",
        "rest_verwijderen": "Remove selected",
        "rest_waarschuwing": ("Note: removed folders and registry keys can only be "
                              "restored from the backup. Check the list carefully."),
        "rest_klaar": "Done: {mappen} folders and {sleutels} keys removed.",
        "rest_klaar_fout": ("Done: {mappen} folders and {sleutels} keys removed, "
                            "{fout} skipped (see log)."),
        "rest_backup_klaar": "Backup made: {pad}",
        "bezig_verwijderen": "Removing...",
        "deinst_bezig": "The uninstaller is running... wait until it finishes.",
        "bezig_zoeken": "Searching leftovers...",
        "geforceerd": "Forced cleanup...",
        "gef_titel": "Forced cleanup",
        "gef_intro": ("For a program you already (partly) removed. Type the name and optionally the publisher; DraveUninstall then searches for leftover folders and registry keys."),
        "gef_naam": "Program name",
        "gef_uitgever": "Publisher (optional)",
        "gef_zoek": "Find leftovers",
        "gef_leeg": "Enter at least a 3-character program name.",
        "kolom_datum": "Installed",
        "batch_klaar": "Finished {n} programs.",
        "terug_titel": "Backups (restore)",
        "terug_intro": ("Choose a backup to restore. Leftover folders are put back "
                        "and the registry keys re-imported."),
        "terug_geen": "No backups yet.",
        "terug_item": "{app}  -  {datum}  -  {mappen} folders, {sleutels} keys  -  {grootte}",
        "terugzetten": "Restore",
        "terug_bevestig": "Restore this backup (folders + registry keys)?",
        "terug_klaar": "Restored: {mappen} folders, {sleutels} keys.",
        "terug_klaar_fout": "Restored: {mappen} folders, {sleutels} keys, {fout} failed.",
        "map_openen": "Open folder",
        "welkom_titel": "Welcome to DraveUninstall",
        "welkom_intro": ("DraveUninstall removes installed programs AND the junk "
                         "Windows leaves behind: leftover folders and registry "
                         "keys. Everything happens locally."),
        "welkom_waarschuwing": ("Note: this program changes the Windows registry and "
                                "deletes folders. Wrong use can damage other "
                                "software. DraveUninstall therefore always makes a "
                                "backup first, and you confirm every step."),
        "welkom_stap1": "1. Pick a program and uninstall it.",
        "welkom_stap2": "2. Review the leftovers carefully before removing anything.",
        "welkom_stap3": "3. Keep the backup on, so you can always go back.",
        "welkom_veilig": ("Safe? Yes - local and offline. Your antivirus may still "
                          "warn about an uninstaller (false alarm); see the Quick "
                          "guide."),
        "welkom_niet_meer": "Do not show this window at startup",
        "welkom_start": "Get started",
        "over_tekst": ("DraveUninstall - complete uninstaller in the Dravenlock "
                       "style. Local, offline, accessible, donationware.\n\n"
                       "Version {versie}\nContact: {contact}\nDonate: {donatie}"),
    },
}


SNELGIDS_NL = """
<h2>DraveUninstall - Snelgids</h2>
<p>DraveUninstall verwijdert programma's compleet: niet alleen de app zelf, maar
ook de <b>restmappen</b> en <b>registersleutels</b> die Windows vaak laat staan.
Alles blijft lokaal; er gaat niets naar internet.</p>
<h3>Zo werkt het</h3>
<ul>
<li><b>1. Kiezen.</b> Selecteer een programma in de lijst (zoeken kan boven).</li>
<li><b>2. De-installeren.</b> Klik op <b>De-installeren</b>. Eerst start de eigen
uninstaller van het programma - doorloop die volledig.</li>
<li><b>3. Restanten opruimen.</b> Daarna zoekt DraveUninstall naar achtergebleven
mappen en registersleutels. Bekijk de lijst goed, laat de <b>back-up</b> aan, en
verwijder wat je echt weg wilt.</li>
</ul>
<h3>Back-up &amp; herstellen</h3>
<p>Voordat restanten worden verwijderd, maakt DraveUninstall een back-up: de
restmappen worden gezipt en de registersleutels naar <b>.reg</b>-bestanden
geexporteerd. Ging er iets mis? Via <b>Back-ups...</b> zet je alles terug
(mappen teruggeplaatst, registersleutels opnieuw geimporteerd).</p>
<h3>Belangrijk</h3>
<ul>
<li>Controleer de restantenlijst <b>altijd zelf</b>. DraveUninstall is
voorzichtig met matchen, maar jij kent je pc het best.</li>
<li>Sommige bestanden/sleutels kunnen <b>in gebruik</b> of <b>beschermd</b> zijn;
die worden overgeslagen en in het logboek vermeld.</li>
<li>Voor systeembrede programma's kan het nodig zijn DraveUninstall <b>als
administrator</b> te starten.</li>
</ul>
<h3>Is dit veilig?</h3>
<p>Ja. DraveUninstall werkt lokaal en offline en stuurt niets naar internet. Je
antivirus of SmartScreen kan toch waarschuwen, omdat het een nieuw,
niet-ondertekend programma is dat bestanden verwijdert en het register wijzigt -
een vals alarm. Bij SmartScreen: <b>Meer informatie -&gt; Toch uitvoeren</b>.</p>
<p>Donatie (vrijwillig): <b>paypal.me/roger076</b> &middot; Contact:
service@dravenlock.nl</p>
"""

SNELGIDS_EN = """
<h2>DraveUninstall - Quick guide</h2>
<p>DraveUninstall removes programs completely: not just the app, but also the
<b>leftover folders</b> and <b>registry keys</b> Windows often leaves behind.
Everything stays local; nothing goes online.</p>
<h3>How it works</h3>
<ul>
<li><b>1. Pick.</b> Select a program in the list (search is at the top).</li>
<li><b>2. Uninstall.</b> Click <b>Uninstall</b>. First the program's own
uninstaller starts - complete it fully.</li>
<li><b>3. Clean leftovers.</b> Then DraveUninstall looks for leftover folders and
registry keys. Review the list, keep the <b>backup</b> on, and remove what you
really want gone.</li>
</ul>
<h3>Backup &amp; restore</h3>
<p>Before leftovers are removed, DraveUninstall makes a backup: leftover folders
are zipped and registry keys exported to <b>.reg</b> files. Something went wrong?
Via <b>Backups...</b> you restore everything (folders put back, keys re-imported).</p>
<h3>Important</h3>
<ul>
<li>Always review the leftover list <b>yourself</b>. DraveUninstall matches
carefully, but you know your PC best.</li>
<li>Some files/keys may be <b>in use</b> or <b>protected</b>; those are skipped
and noted in the log.</li>
<li>For system-wide programs you may need to run DraveUninstall <b>as
administrator</b>.</li>
</ul>
<h3>Is this safe?</h3>
<p>Yes. DraveUninstall works locally and offline and sends nothing online. Your
antivirus or SmartScreen may still warn, because it is a new, unsigned program
that deletes files and changes the registry - a false alarm. For SmartScreen:
<b>More info -&gt; Run anyway</b>.</p>
<p>Donate (voluntary): <b>paypal.me/roger076</b> &middot; Contact:
service@dravenlock.nl</p>
"""


def STIJL():
    return """
* { font-size: 15px; }
QMainWindow, QWidget { background: %(bg)s; color: %(text)s; }
QLabel { color: %(text)s; }
QLabel#titel { font-size: 26px; font-weight: bold; }
QLabel#ondertitel { color: %(muted)s; }
QLabel#uitleg { color: %(muted)s; }
QLabel#strook {
    background: %(panel2)s; color: %(warn)s; border: 1px solid %(line)s;
    border-radius: 8px; padding: 8px 10px;
}
QLabel#waarschuwing {
    background: %(panel2)s; color: %(warn)s; border: 1px solid %(line)s;
    border-radius: 8px; padding: 8px 10px;
}
QPushButton {
    background: %(panel2)s; color: %(text)s; border: 1px solid %(line)s;
    border-radius: 8px; padding: 8px 14px;
}
QPushButton:hover { border-color: %(accent)s; }
QPushButton:disabled { color: %(muted)s; }
QPushButton#primair { background: %(accent)s; color: #0e0e11; font-weight: bold; border: none; }
QPushButton#primair:hover { background: #84b4e0; }
QPushButton#gevaar { background: %(warn)s; color: #0e0e11; font-weight: bold; border: none; }
QPushButton#gevaar:hover { background: #e0a085; }
QLineEdit {
    background: %(panel2)s; color: %(text)s; border: 1px solid %(line)s;
    border-radius: 8px; padding: 8px 10px;
    selection-background-color: %(accent)s; selection-color: #0e0e11;
}
QLineEdit:focus { border-color: %(accent)s; }
QTreeWidget, QListWidget {
    background: %(panel)s; color: %(text)s; border: 1px solid %(line)s;
    border-radius: 8px; outline: none;
}
QTreeWidget::item, QListWidget::item { padding: 5px 4px; }
QTreeWidget::item:selected, QListWidget::item:selected {
    background: %(accent)s; color: #0e0e11;
}
QHeaderView::section {
    background: %(panel2)s; color: %(muted)s; border: none;
    border-bottom: 1px solid %(line)s; padding: 6px;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border: 1px solid %(accent)s;
    border-radius: 4px; background: %(panel2)s;
}
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; }
QTextBrowser {
    background: %(bg)s; color: %(text)s; border: 1px solid %(line)s; border-radius: 8px;
}
QProgressBar {
    background: %(panel2)s; border: 1px solid %(line)s; border-radius: 8px;
    text-align: center; color: %(text)s;
}
QProgressBar::chunk { background: %(accent)s; border-radius: 7px; }
QComboBox {
    background: %(panel2)s; color: %(text)s; border: 1px solid %(line)s;
    border-radius: 6px; padding: 6px 8px;
}
QComboBox QAbstractItemView {
    background: %(panel2)s; color: %(text)s; selection-background-color: %(accent)s;
    selection-color: #0e0e11;
}
QStatusBar { background: %(panel)s; color: %(muted)s; }
QMenuBar { background: %(panel)s; color: %(text)s; }
QMenuBar::item:selected { background: %(panel2)s; }
QMenu { background: %(panel2)s; color: %(text)s; border: 1px solid %(line)s; }
QMenu::item:selected { background: %(accent)s; color: #0e0e11; }
""" % {"bg": BG, "panel": PANEL, "panel2": PANEL2, "text": TEXT, "muted": MUTED,
       "accent": ACCENT, "line": LINE, "warn": WARN}


class LeesThread(QThread):
    klaar = pyqtSignal(list)

    def run(self):
        try:
            apps = lees_programmas()
        except Exception:
            apps = []
        self.klaar.emit(apps)


class RestZoekThread(QThread):
    klaar = pyqtSignal(list, list)   # mappen, sleutels

    def __init__(self, app, forced=False):
        super().__init__()
        self.app = app
        self.forced = forced

    def run(self):
        try:
            mappen = zoek_rest_mappen(self.app)
        except Exception:
            mappen = []
        try:
            sleutels = zoek_rest_sleutels(self.app, eigen=not self.forced)
        except Exception:
            sleutels = []
        self.klaar.emit(mappen, sleutels)


class VerwijderThread(QThread):
    """Back-up maken (optioneel) + restmappen/sleutels verwijderen op de
    achtergrond, zodat de interface niet bevriest bij grote mappen."""
    voortgang = pyqtSignal(str)
    klaar = pyqtSignal(int, int, int, str)   # m_ok, s_ok, fout, backup_pad

    def __init__(self, app, mappen, sleutels, backup_eerst, backup_dir):
        super().__init__()
        self.app = app
        self.mappen = mappen
        self.sleutels = sleutels
        self.backup_eerst = backup_eerst
        self.backup_dir = backup_dir

    def run(self):
        backup_pad = ""
        logregels = ["DraveUninstall - restanten verwijderd",
                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "App: " + self.app.get("naam", ""), "=" * 50]
        if self.backup_eerst:
            self.voortgang.emit("back-up...")
            try:
                backup_pad, _m, _s = maak_backup(self.app, self.mappen,
                                                 self.sleutels, self.backup_dir)
                logregels.append("BACK-UP: " + backup_pad)
            except Exception as e:
                logregels.append("BACK-UP MISLUKT: " + _foutreden(e))
                backup_pad = ""
        m_ok = s_ok = fout = 0
        for m in self.mappen:
            self.voortgang.emit(m)
            _verwijderd, fouten = verwijder_map(m)
            if os.path.isdir(m):
                fout += 1
                logregels.append("MAP DEELS/OVERGESLAGEN: " + m)
                for pad, reden in fouten[:20]:
                    logregels.append("    " + pad + " -> " + reden)
            else:
                m_ok += 1
                logregels.append("MAP VERWIJDERD: " + m)
        for s in self.sleutels:
            self.voortgang.emit(s)
            ok, reden = verwijder_sleutel(s)
            if ok:
                s_ok += 1
                logregels.append("SLEUTEL VERWIJDERD: " + s)
            else:
                fout += 1
                logregels.append("SLEUTEL OVERGESLAGEN: " + s + " -> " + reden)
        try:
            with open(os.path.join(BASIS, "laatste-verwijdering.txt"), "w",
                      encoding="utf-8") as f:
                f.write("\n".join(logregels) + "\n")
        except Exception:
            pass
        self.klaar.emit(m_ok, s_ok, fout, backup_pad)


class UninstallThread(QThread):
    """Start de uninstaller en wacht tot hij klaar is (demo: simuleer)."""
    klaar = pyqtSignal(bool, str)   # gestart_ok, reden

    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self):
        cmd = self.app.get("uninstall_string")
        if not cmd:
            self.klaar.emit(False, "geen uninstall-opdracht")
            return
        if not HEEFT_REGISTER:
            self.msleep(1200)   # demo: doen alsof de uninstaller draait
            self.klaar.emit(True, "(demo)")
            return
        try:
            proc = subprocess.Popen(cmd, shell=True)
            proc.wait()
            self.klaar.emit(True, "")
        except Exception as e:
            self.klaar.emit(False, _foutreden(e))


class ProgrammaItem(QTreeWidgetItem):
    """Lijst-item dat de grootte- en datumkolom numeriek sorteert."""
    def __lt__(self, ander):
        boom = self.treeWidget()
        kol = boom.sortColumn() if boom else 0
        if kol in (3, 4):
            a = self.data(kol, Qt.ItemDataRole.UserRole + 1) or 0
            b = ander.data(kol, Qt.ItemDataRole.UserRole + 1) or 0
            return a < b
        return self.text(kol).lower() < ander.text(kol).lower()


def _pas_palet_toe(app):
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(PANEL2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(BG))
    app.setPalette(pal)


# ---- dialogen ----
class SnelgidsDialoog(QDialog):
    def __init__(self, venster):
        super().__init__(venster)
        self.setWindowTitle(venster.t("snelgids"))
        self.resize(640, 600)
        lay = QVBoxLayout(self)
        b = QTextBrowser()
        b.setOpenExternalLinks(True)
        b.setHtml(SNELGIDS_NL if venster.taal == "nl" else SNELGIDS_EN)
        lay.addWidget(b)


class OverDialoog(QDialog):
    def __init__(self, venster):
        super().__init__(venster)
        self.setWindowTitle(venster.t("over"))
        self.resize(440, 240)
        lay = QVBoxLayout(self)
        lab = QLabel(venster.t("over_tekst").format(
            versie=APP_VERSIE, contact=CONTACT, donatie=DONATIE_URL))
        lab.setWordWrap(True)
        lay.addWidget(lab)
        knop = QPushButton("\u2665 " + venster.t("donatie"))
        knop.setObjectName("primair")
        knop.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATIE_URL)))
        lay.addWidget(knop)


class InstellingenDialoog(QDialog):
    def __init__(self, venster):
        super().__init__(venster)
        self.v = venster
        self.setWindowTitle(venster.t("instellingen"))
        self.resize(420, 180)
        lay = QFormLayout(self)
        self.taal = QComboBox()
        self.taal.addItem(venster.t("taal_auto"), "auto")
        self.taal.addItem("Nederlands", "nl")
        self.taal.addItem("English", "en")
        huidig = venster.cfg_taal
        idx = {"auto": 0, "nl": 1, "en": 2}.get(huidig, 0)
        self.taal.setCurrentIndex(idx)
        lay.addRow(venster.t("taal"), self.taal)
        knoppen = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        knoppen.button(QDialogButtonBox.StandardButton.Save).setText(venster.t("opslaan"))
        knoppen.button(QDialogButtonBox.StandardButton.Cancel).setText(venster.t("annuleren"))
        knoppen.accepted.connect(self._ok)
        knoppen.rejected.connect(self.reject)
        lay.addRow(knoppen)

    def _ok(self):
        self.v.cfg_taal = self.taal.currentData()
        self.accept()


class WelkomDialoog(QDialog):
    def __init__(self, venster):
        super().__init__(venster)
        self.v = venster
        self.setWindowTitle(venster.t("welkom_titel"))
        self.resize(560, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        kop = QHBoxLayout()
        lg = QLabel()
        p = os.path.join(BASIS, "logo.png")
        if os.path.exists(p):
            pm = QPixmap(p)
            if not pm.isNull():
                lg.setPixmap(pm.scaled(QSize(56, 56),
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation))
        kop.addWidget(lg)
        titel = QLabel(venster.t("welkom_titel"))
        titel.setObjectName("titel")
        kop.addWidget(titel)
        kop.addStretch(1)
        lay.addLayout(kop)
        intro = QLabel(venster.t("welkom_intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        waarsch = QLabel(venster.t("welkom_waarschuwing"))
        waarsch.setObjectName("waarschuwing")
        waarsch.setWordWrap(True)
        lay.addWidget(waarsch)
        for s in ("welkom_stap1", "welkom_stap2", "welkom_stap3"):
            lab = QLabel(venster.t(s))
            lab.setWordWrap(True)
            lay.addWidget(lab)
        veilig = QLabel(venster.t("welkom_veilig"))
        veilig.setObjectName("uitleg")
        veilig.setWordWrap(True)
        lay.addWidget(veilig)
        lay.addStretch(1)
        self.chk = QCheckBox(venster.t("welkom_niet_meer"))
        lay.addWidget(self.chk)
        rij = QHBoxLayout()
        rij.addStretch(1)
        start = QPushButton(venster.t("welkom_start"))
        start.setObjectName("primair")
        start.clicked.connect(self.accept)
        rij.addWidget(start)
        lay.addLayout(rij)

    def accept(self):
        if self.chk.isChecked():
            self.v.cfg["toon_welkom"] = False
            bewaar_config(self.v.cfg)
        super().accept()


class RestantenDialoog(QDialog):
    """Toon gevonden restmappen + registersleutels, back-up en verwijderen."""
    def __init__(self, venster, app, mappen, sleutels):
        super().__init__(venster)
        self.v = venster
        self.app = app
        self.setWindowTitle(venster.t("rest_titel"))
        self.resize(640, 560)
        lay = QVBoxLayout(self)

        intro = QLabel(venster.t("rest_intro").format(app=app.get("naam", "")))
        intro.setObjectName("uitleg")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        if not mappen and not sleutels:
            geen = QLabel(venster.t("rest_geen"))
            geen.setWordWrap(True)
            lay.addWidget(geen)
            lay.addStretch(1)
            knop = QPushButton(venster.t("sluit"))
            knop.clicked.connect(self.reject)
            lay.addWidget(knop)
            return

        self.boom = QTreeWidget()
        self.boom.setColumnCount(2)
        self.boom.setHeaderHidden(True)
        self.boom.header().setStretchLastSection(False)
        self.boom.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.boom.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.boom, 1)
        totaal_bytes = 0
        if mappen:
            kop_m = QTreeWidgetItem([venster.t("rest_mappen")])
            kop_m.setFlags(kop_m.flags() | Qt.ItemFlag.ItemIsUserCheckable |
                           Qt.ItemFlag.ItemIsAutoTristate)
            kop_m.setCheckState(0, Qt.CheckState.Checked)
            f = kop_m.font(0); f.setBold(True); kop_m.setFont(0, f)
            self.boom.addTopLevelItem(kop_m)
            for m, bytes_ in mappen:
                totaal_bytes += bytes_
                it = QTreeWidgetItem([m, mensvriendelijke_grootte(bytes_)])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Checked)
                it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight |
                                    Qt.AlignmentFlag.AlignVCenter)
                it.setData(0, Qt.ItemDataRole.UserRole, ("map", m))
                kop_m.addChild(it)
            kop_m.setText(1, mensvriendelijke_grootte(totaal_bytes))
            kop_m.setTextAlignment(1, Qt.AlignmentFlag.AlignRight |
                                   Qt.AlignmentFlag.AlignVCenter)
            kop_m.setExpanded(True)
        if sleutels:
            kop_s = QTreeWidgetItem([venster.t("rest_sleutels")])
            kop_s.setFlags(kop_s.flags() | Qt.ItemFlag.ItemIsUserCheckable |
                           Qt.ItemFlag.ItemIsAutoTristate)
            kop_s.setCheckState(0, Qt.CheckState.Checked)
            f = kop_s.font(0); f.setBold(True); kop_s.setFont(0, f)
            self.boom.addTopLevelItem(kop_s)
            for s in sleutels:
                it = QTreeWidgetItem([s])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, Qt.CheckState.Checked)
                it.setData(0, Qt.ItemDataRole.UserRole, ("sleutel", s))
                kop_s.addChild(it)
            kop_s.setExpanded(True)

        waarsch = QLabel(venster.t("rest_waarschuwing"))
        waarsch.setObjectName("waarschuwing")
        waarsch.setWordWrap(True)
        lay.addWidget(waarsch)

        self.chk_backup = QCheckBox(venster.t("rest_backup_eerst"))
        self.chk_backup.setChecked(True)
        lay.addWidget(self.chk_backup)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("uitleg")
        self.lbl_status.setVisible(False)
        lay.addWidget(self.lbl_status)
        self.balk = QProgressBar()
        self.balk.setRange(0, 0)
        self.balk.setVisible(False)
        lay.addWidget(self.balk)

        rij = QHBoxLayout()
        rij.addStretch(1)
        self.btn_verwijder = QPushButton(venster.t("rest_verwijderen"))
        self.btn_verwijder.setObjectName("gevaar")
        self.btn_verwijder.clicked.connect(self._verwijderen)
        rij.addWidget(self.btn_verwijder)
        self.btn_annuleer = QPushButton(venster.t("annuleren"))
        self.btn_annuleer.clicked.connect(self.reject)
        rij.addWidget(self.btn_annuleer)
        lay.addLayout(rij)
        self.verwijder_thread = None

    def _verzamel(self):
        mappen, sleutels = [], []
        for i in range(self.boom.topLevelItemCount()):
            ouder = self.boom.topLevelItem(i)
            for j in range(ouder.childCount()):
                k = ouder.child(j)
                if k.checkState(0) != Qt.CheckState.Checked:
                    continue
                data = k.data(0, Qt.ItemDataRole.UserRole)
                if not data:
                    continue
                if data[0] == "map":
                    mappen.append(data[1])
                else:
                    sleutels.append(data[1])
        return mappen, sleutels

    def _verwijderen(self):
        mappen, sleutels = self._verzamel()
        if not mappen and not sleutels:
            self.reject()
            return
        self.btn_verwijder.setEnabled(False)
        self.btn_annuleer.setEnabled(False)
        self.lbl_status.setText(self.v.t("bezig_verwijderen"))
        self.lbl_status.setVisible(True)
        self.balk.setVisible(True)
        self.verwijder_thread = VerwijderThread(
            self.app, mappen, sleutels, self.chk_backup.isChecked(),
            backup_map_pad(self.v.cfg))
        self.verwijder_thread.voortgang.connect(self._voortgang)
        self.verwijder_thread.klaar.connect(self._verwijder_klaar)
        self.verwijder_thread.start()

    def _voortgang(self, tekst):
        # toon kort het pad dat nu wordt verwerkt
        if len(tekst) > 60:
            tekst = "..." + tekst[-57:]
        self.lbl_status.setText(tekst)

    def _verwijder_klaar(self, m_ok, s_ok, fout, backup_info):
        self.balk.setVisible(False)
        self.lbl_status.setVisible(False)
        self.btn_annuleer.setEnabled(True)
        if fout:
            tekst = self.v.t("rest_klaar_fout").format(mappen=m_ok, sleutels=s_ok,
                                                       fout=fout)
        else:
            tekst = self.v.t("rest_klaar").format(mappen=m_ok, sleutels=s_ok)
        if backup_info:
            tekst += "\n\n" + self.v.t("rest_backup_klaar").format(pad=backup_info)
        QMessageBox.information(self, APP_NAAM, tekst)
        self.accept()

    def closeEvent(self, e):
        # niet sluiten terwijl er nog verwijderd wordt
        if self.verwijder_thread and self.verwijder_thread.isRunning():
            e.ignore()
            return
        super().closeEvent(e)

    def reject(self):
        if self.verwijder_thread and self.verwijder_thread.isRunning():
            return
        super().reject()


class TerugzetDialoog(QDialog):
    def __init__(self, venster):
        super().__init__(venster)
        self.v = venster
        self.setWindowTitle(venster.t("terug_titel"))
        self.resize(620, 440)
        lay = QVBoxLayout(self)
        intro = QLabel(venster.t("terug_intro"))
        intro.setObjectName("uitleg")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.lijst = QListWidget()
        lay.addWidget(self.lijst, 1)
        self.backups = lees_backups(backup_map_pad(venster.cfg))
        if self.backups:
            for b in self.backups:
                self.lijst.addItem(venster.t("terug_item").format(
                    app=b["app"] or "?", datum=b["datum"] or b["naam"],
                    mappen=b["mappen"], sleutels=b["sleutels"],
                    grootte=mensvriendelijke_grootte(b["grootte"])))
            self.lijst.setCurrentRow(0)
        else:
            self.lijst.addItem(venster.t("terug_geen"))
            self.lijst.setEnabled(False)
        rij = QHBoxLayout()
        btn_map = QPushButton(venster.t("map_openen"))
        btn_map.clicked.connect(self._map)
        rij.addWidget(btn_map)
        rij.addStretch(1)
        self.btn_terug = QPushButton(venster.t("terugzetten"))
        self.btn_terug.setObjectName("primair")
        self.btn_terug.setEnabled(bool(self.backups))
        self.btn_terug.clicked.connect(self._terug)
        rij.addWidget(self.btn_terug)
        btn_sluit = QPushButton(venster.t("sluit"))
        btn_sluit.clicked.connect(self.reject)
        rij.addWidget(btn_sluit)
        lay.addLayout(rij)

    def _map(self):
        mp = backup_map_pad(self.v.cfg)
        os.makedirs(mp, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(mp))

    def _terug(self):
        rij = self.lijst.currentRow()
        if rij < 0 or rij >= len(self.backups):
            return
        if QMessageBox.question(self, self.v.t("terug_titel"),
                                self.v.t("terug_bevestig")) != \
                QMessageBox.StandardButton.Yes:
            return
        m, s, fout = zet_backup_terug(self.backups[rij]["pad"])
        if fout:
            tekst = self.v.t("terug_klaar_fout").format(mappen=m, sleutels=s, fout=fout)
        else:
            tekst = self.v.t("terug_klaar").format(mappen=m, sleutels=s)
        QMessageBox.information(self, APP_NAAM, tekst)


class DeinstallDialoog(QDialog):
    """Bevestiging + uninstaller starten + restanten zoeken."""
    def __init__(self, venster, app):
        super().__init__(venster)
        self.v = venster
        self.app = app
        self.rest_thread = None
        self.setWindowTitle(venster.t("deinst_titel"))
        self.resize(520, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(self._lbl(venster.t("deinst_intro"), "uitleg"))
        naam = QLabel("%s  %s\n%s" % (app.get("naam", ""), app.get("versie", ""),
                                      app.get("uitgever", "")))
        f = naam.font(); f.setBold(True); naam.setFont(f)
        naam.setWordWrap(True)
        lay.addWidget(naam)
        lay.addWidget(self._lbl(venster.t("deinst_stap1"), None))
        lay.addWidget(self._lbl(venster.t("deinst_stap2"), None))
        self.lbl_bezig = QLabel("")
        self.lbl_bezig.setObjectName("uitleg")
        self.lbl_bezig.setVisible(False)
        lay.addWidget(self.lbl_bezig)
        self.balk = QProgressBar(); self.balk.setRange(0, 0); self.balk.setVisible(False)
        lay.addWidget(self.balk)
        lay.addStretch(1)
        rij = QHBoxLayout()
        self.btn_start = QPushButton(venster.t("deinst_start"))
        self.btn_start.setObjectName("primair")
        self.btn_start.clicked.connect(self._start)
        rij.addWidget(self.btn_start)
        self.btn_rest = QPushButton(venster.t("restanten_zoeken"))
        self.btn_rest.setObjectName("gevaar")
        self.btn_rest.setEnabled(True)
        self.btn_rest.clicked.connect(self._zoek_restanten)
        rij.addWidget(self.btn_rest)
        rij.addStretch(1)
        btn_an = QPushButton(venster.t("sluit"))
        btn_an.clicked.connect(self.reject)
        rij.addWidget(btn_an)
        lay.addLayout(rij)
        self.uninstall_thread = None

    def _lbl(self, tekst, obj):
        lab = QLabel(tekst)
        if obj:
            lab.setObjectName(obj)
        lab.setWordWrap(True)
        return lab

    def _start(self):
        self.btn_start.setEnabled(False)
        self.btn_rest.setEnabled(False)
        self.lbl_bezig.setText(self.v.t("deinst_bezig"))
        self.lbl_bezig.setVisible(True)
        self.balk.setVisible(True)
        self.uninstall_thread = UninstallThread(self.app)
        self.uninstall_thread.klaar.connect(self._uninstall_klaar)
        self.uninstall_thread.start()

    def _uninstall_klaar(self, gestart, reden):
        self.balk.setVisible(False)
        self.lbl_bezig.setVisible(False)
        self.btn_start.setEnabled(True)
        self.btn_rest.setEnabled(True)
        if not gestart:
            QMessageBox.warning(self, APP_NAAM,
                                self.v.t("deinst_mislukt").format(reden=reden))
            return
        if not HEEFT_REGISTER:
            QMessageBox.information(self, APP_NAAM,
                                    self.v.t("deinst_demo").format(
                                        cmd=self.app.get("uninstall_string", "")))
        # uninstaller klaar -> meteen restanten zoeken
        self._zoek_restanten()

    def _zoek_restanten(self):
        self.btn_start.setEnabled(False)
        self.btn_rest.setEnabled(False)
        self.lbl_bezig.setText(self.v.t("bezig_zoeken"))
        self.lbl_bezig.setVisible(True)
        self.balk.setVisible(True)
        self.rest_thread = RestZoekThread(self.app)
        self.rest_thread.klaar.connect(self._restanten_klaar)
        self.rest_thread.start()

    def _restanten_klaar(self, mappen, sleutels):
        self.balk.setVisible(False)
        self.lbl_bezig.setVisible(False)
        self.btn_start.setEnabled(True)
        self.btn_rest.setEnabled(True)
        d = RestantenDialoog(self.v, self.app, mappen, sleutels)
        d.exec()
        self.accept()


class GeforceerdeDialoog(QDialog):
    """Restanten opsporen voor een (al verwijderd) programma op naam/uitgever."""
    def __init__(self, venster):
        super().__init__(venster)
        self.v = venster
        self.rest_thread = None
        self.pseudo = None
        self.setWindowTitle(venster.t("gef_titel"))
        self.resize(520, 280)
        lay = QVBoxLayout(self)
        intro = QLabel(venster.t("gef_intro"))
        intro.setObjectName("uitleg")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.veld_naam = QLineEdit()
        self.veld_uitgever = QLineEdit()
        form.addRow(venster.t("gef_naam"), self.veld_naam)
        form.addRow(venster.t("gef_uitgever"), self.veld_uitgever)
        lay.addLayout(form)
        self.lbl_bezig = QLabel("")
        self.lbl_bezig.setObjectName("uitleg")
        self.lbl_bezig.setVisible(False)
        lay.addWidget(self.lbl_bezig)
        self.balk = QProgressBar(); self.balk.setRange(0, 0); self.balk.setVisible(False)
        lay.addWidget(self.balk)
        lay.addStretch(1)
        rij = QHBoxLayout()
        rij.addStretch(1)
        self.btn_zoek = QPushButton(venster.t("gef_zoek"))
        self.btn_zoek.setObjectName("gevaar")
        self.btn_zoek.clicked.connect(self._zoek)
        rij.addWidget(self.btn_zoek)
        btn_sluit = QPushButton(venster.t("sluit"))
        btn_sluit.clicked.connect(self.reject)
        rij.addWidget(btn_sluit)
        lay.addLayout(rij)

    def _zoek(self):
        naam = self.veld_naam.text().strip()
        if len(naam) < 3:
            QMessageBox.information(self, APP_NAAM, self.v.t("gef_leeg"))
            return
        self.pseudo = {
            "naam": naam,
            "uitgever": self.veld_uitgever.text().strip(),
            "versie": "", "grootte_bytes": 0, "datum": "",
            "installatielocatie": "",
            "uninstall_string": "", "quiet": "",
            "bron": "", "hive": "HKCU", "sleutel_pad": "SOFTWARE",
            "sleutel_naam": "",
        }
        self.btn_zoek.setEnabled(False)
        self.lbl_bezig.setText(self.v.t("bezig_zoeken"))
        self.lbl_bezig.setVisible(True)
        self.balk.setVisible(True)
        self.rest_thread = RestZoekThread(self.pseudo, forced=True)
        self.rest_thread.klaar.connect(self._klaar)
        self.rest_thread.start()

    def _klaar(self, mappen, sleutels):
        self.balk.setVisible(False)
        self.lbl_bezig.setVisible(False)
        self.btn_zoek.setEnabled(True)
        RestantenDialoog(self.v, self.pseudo, mappen, sleutels).exec()


class Hoofdvenster(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = laad_config()
        self.cfg_taal = self.cfg.get("taal", "auto")
        self.taal = (self.cfg_taal if self.cfg_taal in ("nl", "en")
                     else detecteer_taal())
        self.apps = []
        self.lees_thread = None
        self.setWindowTitle("%s  v%s" % (APP_NAAM, APP_VERSIE))
        self.resize(940, 640)
        ico = os.path.join(BASIS, "app.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        self.setStyleSheet(STIJL())
        self._bouw()
        self._menu()
        QTimer.singleShot(0, self.start_lezen)

    def t(self, sleutel):
        return TEKST.get(self.taal, TEKST["en"]).get(sleutel, sleutel)

    def _bouw(self):
        centraal = QWidget()
        self.setCentralWidget(centraal)
        lay = QVBoxLayout(centraal)
        # kop
        kop = QHBoxLayout()
        logo = QLabel()
        p = os.path.join(BASIS, "logo.png")
        if os.path.exists(p):
            pm = QPixmap(p)
            if not pm.isNull():
                logo.setPixmap(pm.scaled(QSize(48, 48),
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
        kop.addWidget(logo)
        titels = QVBoxLayout()
        t1 = QLabel(APP_NAAM); t1.setObjectName("titel")
        t2 = QLabel(self.t("ondertitel")); t2.setObjectName("ondertitel")
        titels.addWidget(t1); titels.addWidget(t2)
        kop.addLayout(titels)
        kop.addStretch(1)
        lay.addLayout(kop)
        # knoppen
        knoppen = QHBoxLayout()
        self.btn_vernieuw = QPushButton(self.t("vernieuwen"))
        self.btn_vernieuw.clicked.connect(self.start_lezen)
        knoppen.addWidget(self.btn_vernieuw)
        self.btn_deinst = QPushButton(self.t("deinstalleren"))
        self.btn_deinst.setObjectName("gevaar")
        self.btn_deinst.clicked.connect(self._deinstalleren)
        knoppen.addWidget(self.btn_deinst)
        self.btn_gef = QPushButton(self.t("geforceerd"))
        self.btn_gef.clicked.connect(self._geforceerd)
        knoppen.addWidget(self.btn_gef)
        knoppen.addStretch(1)
        self.btn_backups = QPushButton(self.t("backups"))
        self.btn_backups.clicked.connect(lambda: TerugzetDialoog(self).exec())
        knoppen.addWidget(self.btn_backups)
        lay.addLayout(knoppen)
        # demo-strook
        if not HEEFT_REGISTER:
            strook = QLabel(self.t("demo_strook"))
            strook.setObjectName("strook")
            strook.setWordWrap(True)
            lay.addWidget(strook)
        # zoek
        self.zoek = QLineEdit()
        self.zoek.setPlaceholderText(self.t("zoek"))
        self.zoek.textChanged.connect(self._filter)
        lay.addWidget(self.zoek)
        # lijst
        self.boom = QTreeWidget()
        self.boom.setColumnCount(6)
        self.boom.setHeaderLabels([self.t("kolom_naam"), self.t("kolom_uitgever"),
                                   self.t("kolom_versie"), self.t("kolom_grootte"),
                                   self.t("kolom_datum"), self.t("kolom_bron")])
        self.boom.setRootIsDecorated(False)
        self.boom.setAlternatingRowColors(False)
        self.boom.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.boom.setSortingEnabled(True)
        self.boom.itemDoubleClicked.connect(lambda *_: self._deinstalleren())
        kop_h = self.boom.header()
        kop_h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4, 5):
            kop_h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.boom, 1)
        # statusbalk
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_links = QLabel("")
        sb.addWidget(self.status_links)
        self.btn_donatie = QPushButton(" \u2665 " + self.t("donatie"))
        self.btn_donatie.setObjectName("primair")
        self.btn_donatie.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(DONATIE_URL)))
        sb.addPermanentWidget(self.btn_donatie)

    def _menu(self):
        mb = self.menuBar()
        m_inst = mb.addMenu(self.t("menu_inst"))
        a_inst = QAction(self.t("instellingen"), self)
        a_inst.triggered.connect(self._instellingen)
        m_inst.addAction(a_inst)
        a_back = QAction(self.t("backups"), self)
        a_back.triggered.connect(lambda: TerugzetDialoog(self).exec())
        m_inst.addAction(a_back)
        m_inst.addSeparator()
        a_sluit = QAction(self.t("sluiten"), self)
        a_sluit.setShortcut("Ctrl+Q")
        a_sluit.triggered.connect(self.close)
        m_inst.addAction(a_sluit)
        m_help = mb.addMenu(self.t("menu_help"))
        a_gids = QAction(self.t("snelgids"), self)
        a_gids.setShortcut("F1")
        a_gids.triggered.connect(lambda: SnelgidsDialoog(self).exec())
        m_help.addAction(a_gids)
        a_welkom = QAction(self.t("welkom_menu"), self)
        a_welkom.triggered.connect(lambda: WelkomDialoog(self).exec())
        m_help.addAction(a_welkom)
        a_don = QAction("\u2665 " + self.t("donatie"), self)
        a_don.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(DONATIE_URL)))
        m_help.addAction(a_don)
        a_over = QAction(self.t("over"), self)
        a_over.triggered.connect(lambda: OverDialoog(self).exec())
        m_help.addAction(a_over)

    # ---- programma's lezen ----
    def start_lezen(self):
        if self.lees_thread and self.lees_thread.isRunning():
            return
        self.boom.clear()
        self.btn_vernieuw.setEnabled(False)
        self.status_links.setText(self.t("bezig_lezen"))
        self.lees_thread = LeesThread()
        self.lees_thread.klaar.connect(self._lezen_klaar)
        self.lees_thread.start()

    def _lezen_klaar(self, apps):
        self.apps = apps
        self.btn_vernieuw.setEnabled(True)
        self.boom.setSortingEnabled(False)
        self.boom.clear()
        for a in apps:
            it = ProgrammaItem([
                a.get("naam", ""), a.get("uitgever", ""), a.get("versie", ""),
                mensvriendelijke_grootte(a.get("grootte_bytes", 0)),
                datum_opmaak(a.get("datum", "")), a.get("bron", "")])
            it.setData(0, Qt.ItemDataRole.UserRole, a)
            it.setData(3, Qt.ItemDataRole.UserRole + 1, a.get("grootte_bytes", 0))
            it.setData(4, Qt.ItemDataRole.UserRole + 1, datum_sorteer(a.get("datum", "")))
            self.boom.addTopLevelItem(it)
        self.boom.setSortingEnabled(True)
        self.boom.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.status_links.setText(self.t("klaar_lezen").format(n=len(apps)))

    def _filter(self, tekst):
        t = tekst.strip().lower()
        for i in range(self.boom.topLevelItemCount()):
            it = self.boom.topLevelItem(i)
            zichtbaar = (t in it.text(0).lower() or t in it.text(1).lower())
            it.setHidden(bool(t) and not zichtbaar)

    def _geselecteerde_apps(self):
        apps = []
        for it in self.boom.selectedItems():
            a = it.data(0, Qt.ItemDataRole.UserRole)
            if a and a not in apps:
                apps.append(a)
        return apps

    def _deinstalleren(self):
        apps = self._geselecteerde_apps()
        if not apps:
            QMessageBox.information(self, APP_NAAM, self.t("niets_geselecteerd"))
            return
        verwerkt = 0
        for a in apps:
            d = DeinstallDialoog(self, a)
            if d.exec() != QDialog.DialogCode.Accepted:
                break   # gebruiker bedacht zich -> hele reeks stoppen
            verwerkt += 1
        if verwerkt > 1:
            QMessageBox.information(self, APP_NAAM,
                                   self.t("batch_klaar").format(n=verwerkt))
        self.start_lezen()

    def _geforceerd(self):
        GeforceerdeDialoog(self).exec()
        self.start_lezen()

    def _instellingen(self):
        d = InstellingenDialoog(self)
        if d.exec():
            self.cfg["taal"] = self.cfg_taal
            bewaar_config(self.cfg)
            self.taal = (self.cfg_taal if self.cfg_taal in ("nl", "en")
                         else detecteer_taal())
            QMessageBox.information(self, APP_NAAM, "OK")
            # eenvoudig: labels verversen via herstart-hint niet nodig; herbouw kop
            self.setWindowTitle("%s  v%s" % (APP_NAAM, APP_VERSIE))

    def closeEvent(self, e):
        if self.lees_thread and self.lees_thread.isRunning():
            self.lees_thread.wait(1500)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAAM)
    _pas_palet_toe(app)
    v = Hoofdvenster()
    v.show()
    if v.cfg.get("toon_welkom", True):
        QTimer.singleShot(0, lambda: WelkomDialoog(v).exec())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
