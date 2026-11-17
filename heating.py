"""
Θέρμανση: τι συμφέρει. Κόστος για την ίδια ζέστη με διαφορετικά συστήματα.

Οι τιμές ρεύματος και αερίου βγαίνουν από τα καλύτερα προγράμματα της εφαρμογής (με όλες τις χρεώσεις),
οι υπόλοιπες είναι ενδεικτικές και τις αλλάζει ο χρήστης.
"""
import engine
import store

# ζώνες ΚΕΝΑΚ και συντελεστής σε σχέση με τη ζώνη Β (Αθήνα)
ZONES = {
    "Α (Κρήτη, Δωδεκάνησα, νότια παράλια)": 0.65,
    "Β (Αθήνα, Πελοπόννησος, Ιόνιο, Κυκλάδες)": 1.0,
    "Γ (Θεσσαλονίκη, Θεσσαλία, Ήπειρος, Θράκη)": 1.45,
    "Δ (Φλώρινα, Κοζάνη, Καστοριά, ορεινά)": 1.9,
}
# ανάγκη θέρμανσης ζώνης Β σε kWh θερμότητας ανά m² τον χρόνο
INSULATION = {"Χωρίς μόνωση (παλιό σπίτι)": 110, "Μέτρια μόνωση": 75, "Καλή μόνωση (νεόδμητο)": 45}

DEFAULT_PRICES = {"oil": 1.12, "pellet": 320.0, "wood": 190.0}

# κλειδί: (όνομα, πώς πληρώνεται, kWh ανά μονάδα, απόδοση/SCOP, ετήσια συντήρηση €)
SYSTEMS = {
    "oil": ("Πετρέλαιο (λέβητας καλοριφέρ)", "€/λίτρο", 10.0, 0.85, 80),
    "gas": ("Φυσικό αέριο (λέβητας συμπύκνωσης)", "€/kWh", 1.0, 0.95, 60),
    "heatpump": ("Αντλία θερμότητας (αέρα-νερού)", "€/kWh ρεύματος", 1.0, 3.3, 80),
    "ac": ("Κλιματιστικό inverter", "€/kWh ρεύματος", 1.0, 3.5, 30),
    "pellet": ("Πέλλετ (σόμπα ή λέβητας)", "€/τόνο", 4800.0, 0.88, 60),
    "wood": ("Καυσόξυλα (σόμπα / ενεργειακό τζάκι)", "€/τόνο", 4000.0, 0.70, 40),
    "electric": ("Ηλεκτρικά σώματα / καλοριφέρ λαδιού", "€/kWh ρεύματος", 1.0, 1.0, 0),
}
COLORS = {"oil": (0.45, 0.35, 0.3, 1), "gas": (0.15, 0.55, 0.9, 1), "heatpump": (0.1, 0.7, 0.5, 1),
          "ac": (0.2, 0.75, 0.8, 1), "pellet": (0.85, 0.55, 0.15, 1), "wood": (0.65, 0.35, 0.15, 1),
          "electric": (0.85, 0.25, 0.25, 1)}


def heat_need(m2, zone, insulation):
    """Ετήσια θερμότητα που χρειάζεται το σπίτι (kWh)."""
    return max(20, m2) * INSULATION.get(insulation, 75) * ZONES.get(zone, 1.0)


def heat_from_oil(litres):
    """Αν ξέρεις πόσο πετρέλαιο καις τον χρόνο: η πραγματική ανάγκη του σπιτιού σου."""
    return litres * SYSTEMS["oil"][2] * SYSTEMS["oil"][3]


def _marginal(service, d, step):
    """Πόσο κοστίζει μια επιπλέον kWh με το καλύτερο πρόγραμμα (μαζί με ρυθμιζόμενες χρεώσεις και φόρους)."""
    prof = dict(d["profile"])
    rows = engine.ranked(service, store.data_of(d).get(service, []), prof)
    if not rows:
        return None, None
    best = rows[0]
    key = "kwh_month" if service == "electricity" else "gas_kwh_year"
    base = prof[key]
    c0 = engine.plan_cost(service, best, prof, False)
    prof2 = dict(prof)
    prof2[key] = base + step
    c1 = engine.plan_cost(service, best, prof2, False)
    per = (c1 - c0) / step                                 # €/μήνα ανά kWh/μήνα (ρεύμα) ή ανά kWh/έτος (αέριο)
    if service == "gas":
        per *= 12                                          # το κόστος του αερίου είναι μηνιαίο, η ποσότητα ετήσια
    return max(0.0, per), best


def prices(d, user=None):
    """Τιμή ανά μονάδα για κάθε σύστημα."""
    user = user or {}
    el, el_plan = _marginal("electricity", d, 100.0)
    ga, ga_plan = _marginal("gas", d, 1000.0)
    out = {"oil": user.get("oil", DEFAULT_PRICES["oil"]), "pellet": user.get("pellet", DEFAULT_PRICES["pellet"]),
           "wood": user.get("wood", DEFAULT_PRICES["wood"])}
    out.update(electricity=user.get("electricity", round(el, 4) if el else 0.20),
               gas=user.get("gas", round(ga, 4) if ga else 0.09))
    src = {"electricity": el_plan["provider"] + " " + el_plan["name"] if el_plan else "",
           "gas": ga_plan["provider"] + " " + ga_plan["name"] if ga_plan else ""}
    return out, src


def compare(need_kwh, pr, zone):
    """[(κλειδί, όνομα, ετήσιο κόστος, κόστος ανά kWh θερμότητας, μονάδες τον χρόνο, μονάδα)] από το φθηνότερο."""
    cold = ZONES.get(zone, 1.0) >= 1.9
    res = []
    for k, (name, unit, kwh_unit, eff, service) in SYSTEMS.items():
        if k in ("heatpump", "ac") and cold:
            eff = eff * 0.82                                 # πολύ κρύο: χαμηλότερη απόδοση
        price = pr["electricity"] if unit == "€/kWh ρεύματος" else (pr["gas"] if k == "gas" else pr[k])
        per_kwh_heat = price / kwh_unit / eff                # ίδιος τύπος για λίτρα, kWh και τόνους
        if unit == "€/τόνο":
            units, unit_name = need_kwh / (kwh_unit / 1000 * eff), "κιλά"
        elif k == "oil":
            units, unit_name = need_kwh / (kwh_unit * eff), "λίτρα"
        else:
            units, unit_name = need_kwh / eff, "kWh"
        res.append((k, name, need_kwh * per_kwh_heat + service, per_kwh_heat, units, unit_name))
    return sorted(res, key=lambda r: r[2])


NOTES = [
    "Δεν περιλαμβάνεται το κόστος αγοράς και εγκατάστασης του συστήματος.",
    "Η αντλία θερμότητας και το κλιματιστικό αποδίδουν λιγότερο σε πολύ κρύες περιοχές (ζώνη Δ).",
    "Τα καυσόξυλα πρέπει να είναι ξερά: τα υγρά δίνουν πολύ λιγότερη θερμότητα.",
    "Ο υπολογισμός είναι εκτίμηση. Αν ξέρεις πόσο πετρέλαιο καις τον χρόνο, γράψ' το για πιο ακριβές αποτέλεσμα.",
]
