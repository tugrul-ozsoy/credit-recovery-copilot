"""Naive consolidated absolute-priority waterfall, inputs hand-copied from extracted text above.
Checks whether a simple engine reproduces the debtor's filed per-class recovery %."""
def wf(ndv, tiers):
    out = []
    for name, claims in tiers:          # tier = list of (class, claim) paid pari passu
        tot = sum(c for _, c in claims); pay = min(ndv, tot); ndv -= pay
        for cls, c in claims: out.append((name, cls, round(100 * pay / tot, 1) if tot else None))
    return out
cases = {
 "WW (low/mid/high, $000)": ([119352, 143650, 177911], [
    ("secured", [("Revolver", 178091), ("1L TL", 946478), ("4.5% SSN", 501375)]),
    ("admin+priority", [("Admin&Priority", 95525)]),
    ("GUC", [("GUC (low end)", 1487081)])], "filed: secured 7/9/11%, admin 0%, GUC 0%"),
 "Wolfspeed (low/high, $000)": ([1431121, 2760730], [
    ("secured", [("Sr Secured Notes", 1811576)]),
    ("admin+priority", [("Admin", 56980), ("Other Secured", 119081), ("Priority Tax", 15333), ("Grants", 549500)]),
    ("unsecured", [("Converts+deposits+GUC", 5526165)])], "filed: SSN 79.0/100%, admin 0/100%, unsecured 0/3.8%"),
 "Enviva (low/mid/high, $mm)": ([234.9, 290.5, 364.3], [
    ("DIP", [("DIP", 507.7)]),
    ("other secured", [("Revolver", 579.3), ("TL", 105.5), ("NMTC QLICI", 42.1), ("NMTC Source", 30.8), ("FiberCo", 3.4)])],
    "filed: DIP 18.0/18.6/19.1%, Revolver 15.5/21.2/29.6%, NMTC QLICI 51.1/70.6/89.5% (entity-level waterfalls)"),
}
for k, (ndvs, tiers, filed) in cases.items():
    print("==", k, "|", filed)
    for ndv in ndvs: print("   NDV", ndv, "->", [(c, r) for _, c, r in wf(ndv, tiers)])
