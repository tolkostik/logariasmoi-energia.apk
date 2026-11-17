"""
Όλα τα έξοδα του σπιτιού και υπενθυμίσεις πληρωμών.

Κάθε έξοδο: όνομα, κατηγορία, ποσό, κάθε πόσους μήνες, επόμενη λήξη (προαιρετικά), ιστορικό πληρωμών.
Τα 4 βασικά (ρεύμα, αέριο, internet, κινητή) συγχρονίζονται με το «Πόσα πληρώνω σήμερα».
"""
import calendar
import datetime
import time

CATS = [
    # (κατηγορία, χρώμα, υπηρεσία εφαρμογής που αντιστοιχεί)
    ("Ρεύμα", (0.98, 0.7, 0.1, 1), "electricity"),
    ("Φυσικό αέριο", (0.15, 0.55, 0.9, 1), "gas"),
    ("Internet", (0.1, 0.7, 0.75, 1), "internet"),
    ("Κινητή", (0.55, 0.35, 0.9, 1), "mobile"),
    ("Νερό", (0.25, 0.75, 0.95, 1), None),
    ("Κοινόχρηστα", (0.45, 0.6, 0.35, 1), None),
    ("Ενοίκιο / δάνειο", (0.85, 0.3, 0.3, 1), None),
    ("Θέρμανση (πετρέλαιο, πέλλετ…)", (0.6, 0.4, 0.25, 1), None),
    ("Ασφάλειες", (0.3, 0.4, 0.7, 1), None),
    ("Συνδρομές TV / streaming", (0.9, 0.35, 0.6, 1), None),
    ("Φόροι & τέλη (ΕΝΦΙΑ, δημοτικά)", (0.5, 0.5, 0.55, 1), None),
    ("Άλλο", (0.65, 0.65, 0.7, 1), None),
]
CAT_COLOR = {c: col for c, col, _ in CATS}
CAT_SERVICE = {c: s for c, _, s in CATS if s}
FREQS = {"Κάθε μήνα": 1, "Κάθε 2 μήνες": 2, "Κάθε 3 μήνες": 3, "Κάθε 6 μήνες": 6, "Μία φορά τον χρόνο": 12}
FREQ_NAME = {v: k for k, v in FREQS.items()}


def items(d):
    return d.setdefault("expenses", [])


def parse_date(s):
    try:
        return datetime.datetime.strptime((s or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def add_months(dt, m):
    y, mo = divmod(dt.month - 1 + m, 12)
    day = min(dt.day, calendar.monthrange(dt.year + y, mo + 1)[1])
    return datetime.date(dt.year + y, mo + 1, day)


def monthly(it):
    try:
        return float(it.get("amount") or 0) / max(1, int(it.get("freq") or 1))
    except (TypeError, ValueError):
        return 0.0


def upsert(d, it):
    lst = items(d)
    if not it.get("id"):
        it["id"] = int(time.time() * 1000) + len(lst)
        lst.append(it)
    else:
        for i, x in enumerate(lst):
            if x["id"] == it["id"]:
                lst[i] = it
    sync_current(d)
    return it


def delete(d, iid):
    d["expenses"] = [x for x in items(d) if x["id"] != iid]
    sync_current(d)


def seed_from_current(d):
    """Την πρώτη φορά: τα ποσά του «Πόσα πληρώνω σήμερα» γίνονται έξοδα."""
    if d.get("expenses_seeded"):
        return
    have = {x["cat"] for x in items(d)}
    for cat, svc in CAT_SERVICE.items():
        v = (d.get("current") or {}).get(svc)
        if v and cat not in have:
            upsert(d, {"name": cat, "cat": cat, "amount": float(v), "freq": 1, "due": "", "history": []})
    d["expenses_seeded"] = True


def sync_current(d):
    """Τα έξοδα ρεύματος/αερίου/internet/κινητής ενημερώνουν τη σύγκριση εξοικονόμησης."""
    cur = d.setdefault("current", {})
    sums = {}
    for it in items(d):
        svc = CAT_SERVICE.get(it.get("cat"))
        if svc:
            sums[svc] = sums.get(svc, 0.0) + monthly(it)
    for svc, v in sums.items():
        cur[svc] = round(v, 2)


def totals(d):
    by = {}
    for it in items(d):
        by[it["cat"]] = by.get(it["cat"], 0.0) + monthly(it)
    month = sum(by.values())
    return {"month": month, "year": month * 12,
            "by_cat": sorted(by.items(), key=lambda kv: -kv[1])}


# ------------------------------------------------------------------ υπενθυμίσεις
def status(it, today=None):
    """(επίπεδο 'late'|'today'|'soon'|'later'|None, ημέρες, κείμενο)"""
    due = parse_date(it.get("due"))
    if not due:
        return None, None, ""
    days = (due - (today or datetime.date.today())).days
    if days < 0:
        return "late", days, f"έληξε πριν από {-days} {'ημέρα' if days == -1 else 'ημέρες'}"
    if days == 0:
        return "today", 0, "λήγει σήμερα"
    if days <= 7:
        return "soon", days, f"λήγει σε {days} {'ημέρα' if days == 1 else 'ημέρες'}"
    return "later", days, f"λήγει {due:%d/%m}"


def upcoming(d, within=7):
    out = []
    for it in items(d):
        lv, days, txt = status(it)
        if lv in ("late", "today", "soon") or (lv == "later" and days <= within):
            out.append((it, lv, days, txt))
    return sorted(out, key=lambda t: t[2])


def mark_paid(d, iid, amount=None):
    for it in items(d):
        if it["id"] == iid:
            due = parse_date(it.get("due")) or datetime.date.today()
            it.setdefault("history", []).append({"date": datetime.date.today().strftime("%d/%m/%Y"),
                                                 "amount": float(amount if amount is not None else it.get("amount") or 0),
                                                 "for": due.strftime("%d/%m/%Y")})
            it["history"] = it["history"][-36:]
            if it.get("due"):
                nxt = add_months(due, int(it.get("freq") or 1))
                while nxt < datetime.date.today():
                    nxt = add_months(nxt, int(it.get("freq") or 1))
                it["due"] = nxt.strftime("%d/%m/%Y")
            return it
    return None


def paid_this_year(d):
    y = datetime.date.today().year
    tot = 0.0
    for it in items(d):
        for h in it.get("history", []):
            dt = parse_date(h.get("date"))
            if dt and dt.year == y:
                tot += h.get("amount", 0)
    return tot


def from_current(d):
    """Όταν αλλάζουν τα ποσά στο «Πόσα πληρώνω σήμερα», ενημερώνονται και τα αντίστοιχα έξοδα."""
    cur = d.get("current") or {}
    for cat, svc in CAT_SERVICE.items():
        v = cur.get(svc)
        same = [x for x in items(d) if x.get("cat") == cat]
        if v in (None, "", 0):
            continue
        if not same:
            items(d).append({"id": int(time.time() * 1000) + len(items(d)), "name": cat, "cat": cat,
                             "amount": float(v), "freq": 1, "due": "", "history": []})
        elif len(same) == 1:
            it = same[0]
            it["amount"] = round(float(v) * max(1, int(it.get("freq") or 1)), 2)
