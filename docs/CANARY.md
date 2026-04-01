## Warrant Canary — Social-Hunt

Status: ACTIVE
Last updated (UTC): 2026-04-01

---

### What this is

This document is a transparency canary for the Social-Hunt project maintainers.
It is updated quarterly. If this file is removed, altered without a new signed
version, or not refreshed within 90 days of the date above, treat the canary as
**stale** and do not assume any particular legal status for the project.

---

### Quarterly Statements (as of 2026-04-01 UTC)

- We have received **0** legal demands, subpoenas, or court orders for user data.
- We have received **0** gag orders or equivalent non-disclosure restrictions.
- We have received **0** National Security Letters or equivalent secret demands.
- We have received **0** data preservation requests from any government or agency.
- We have received **0** takedown demands (DMCA or otherwise) relating to user data.
- The Social-Hunt codebase has **not** been backdoored, modified under compulsion,
  or altered in any way we have been prohibited from disclosing.
- No law enforcement access to project infrastructure has been granted.

---

### Project Release Activity (Q1 2026)

- 2026-01-27: v2.2.0 released — dependency security patches (protobuf, starlette).
- 2026-04-01: v2.2.3 released — Voter Records portal directory, Google Dorks
  enhancements, Breach Search improvements, README rewrite, bug fixes.

---

### Signers (maintainers)

| Name                | Email                              | PGP Fingerprint                            |
|---------------------|------------------------------------|--------------------------------------------|
| AfterPacketTru      | AfterPacketTru@protonmail.com      | C46C 734A 833D CFDC C944 E08C E708 D247 1A06 73CB |
| airborne-commando   | photonman096@proton.me             | AA31 A1EF 7719 DC5F A789 BBFB AE8C 320A DAD3 4A5F |

---

### How to verify this canary

1. Import the AfterPacket public key:

```
-----BEGIN PGP PUBLIC KEY BLOCK-----

xjMEZ742yRYJKwYBBAHaRw8BAQdAM0mQoiR+LdBbhaHawEa5Mth4gZsCbGGE
ooqMWdpiAoPNPUFmdGVyUGFja2V0VHJ1QHByb3Rvbm1haWwuY29tIDxBZnRl
clBhY2tldFRydUBwcm90b25tYWlsLmNvbT7CwBEEExYKAIMFgme+NskDCwkH
CZDnCNJHGgZzy0UUAAAAAAAcACBzYWx0QG5vdGF0aW9ucy5vcGVucGdwanMu
b3JnPZi0AfTaiR1f6BzrDS9wPsmG1JihHg5qXj8s0QyLrE8DFQoIBBYAAgEC
GQECmwMCHgEWIQTEbHNKgz3P3MlE4IznCNJHGgZzywAAkdQBAOpxsX1QSvS1
uqJRWO5ip1Ken0GoQ53PAeq+0X0qZjHYAQDxYcHZJtTocAVQmDOVckyHLdLl
jiVd1ji9Qc2zV6huCM44BGe+NskSCisGAQQBl1UBBQEBB0D9TmsElkctIRCj
8b1xAUeU34Ppnh/IM+A/wFDCfdpLCwMBCAfCvgQYFgoAcAWCZ742yQmQ5wjS
RxoGc8tFFAAAAAAAHAAgc2FsdEBub3RhdGlvbnMub3BlbnBncGpzLm9yZyaB
cmVMcE/QzpDaFYjwSKxBXUzo4/bmHLE/tr7NH3QAApsMFiEExGxzSoM9z9zJ
ROCM5wjSRxoGc8sAAHNqAQDwFxm/6JFPEmWeq8xXwx4UNKGAHNgSq1kT5InO
hNCXRgD/VJoQMFO6UDD4HEHJ/6j4z2hD3BoYeJDdRWVhjeISaQU=
=rxGq
-----END PGP PUBLIC KEY BLOCK-----
```

2. Verify the PGP-signed commit or attached detached signature for this file using:

   ```bash
   gpg --import afterpacket.asc
   gpg --verify CANARY.md.sig CANARY.md
   ```

3. Confirm the fingerprint matches:
   `C46C 734A 833D CFDC C944 E08C E708 D247 1A06 73CB`

---

### Signing instructions (maintainers)

To produce a new signed canary:

```bash
# Clearsign (self-contained)
gpg --clearsign --local-user AfterPacketTru@protonmail.com docs/CANARY.md

# Or detached signature
gpg --detach-sign --armor --local-user AfterPacketTru@protonmail.com docs/CANARY.md
# produces docs/CANARY.md.asc — commit both files
```

---

### Next scheduled update

2026-07-01 (90 days)

---

*Social-Hunt — https://github.com/AfterPacket/Social-Hunt*
*GPL-3.0 License*