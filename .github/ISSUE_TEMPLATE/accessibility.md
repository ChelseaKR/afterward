---
name: Accessibility problem
about: Something is hard or impossible to use
title: 'A11y: '
labels: accessibility
---

**What happened, and what did you expect?**

**Where?** URL, and English or Spanish.

**What are you using?** Browser and version, and screen reader / magnification / voice control
/ keyboard-only if any. "I do not know, it is the one that came with my phone" is a useful
answer — say that rather than nothing.

---

This site targets WCAG 2.2 AAA and gates every build on it, but the automation cannot test
what an actual screen reader announces, and no automated tool can. A report from someone
using one carries more weight here than the entire audit suite. It will not be closed as
"passes axe".
