# 11 License And Risk Notice

This document does two things:

1. clarifies the DeepScientist open-source license and responsibility boundary
2. lists the main risks that you, not the project maintainers, must control

This is not legal advice. If you plan to use DeepScientist in a company environment, production environment, external-facing service, or regulated workflow, have your own legal, security, and operations teams review it again.

## 1. License And Responsibility Boundary

DeepScientist is released under the Apache License 2.0.

The full license text is in the repository root:

- [LICENSE](../../LICENSE)
- [TRADEMARK.md](../../TRADEMARK.md)
- [26 Citation And Attribution](./26_CITATION_AND_ATTRIBUTION.md)

The practical meaning is:

- DeepScientist is distributed under Apache 2.0
- the software license does not grant trademark rights in the DeepScientist name or logo
- citation guidance is a separate academic attribution request, not an extra software license condition
- DeepScientist is provided on an "AS IS" basis, without warranties
- the project authors and maintainers are not responsible for any direct or indirect consequence caused by using, deploying, modifying, redistributing, or exposing DeepScientist
- you are responsible for runtime environment control, permission boundaries, public exposure, third-party account binding, output review, data handling, and compliance

In other words, DeepScientist is a high-capability automation system. It is not a managed service and it is not a security-audited guarantee layer. You must control the operating boundary yourself.

## 2. Main Risk Areas

These risks are real, and they compound each other.

### 2.1 Host And Server Damage

DeepScientist can drive models to execute commands, modify files, install dependencies, run scripts, and read or write project directories.

That means it can:

- delete, overwrite, or corrupt files
- modify Git state, branches, or worktree contents
- install the wrong dependency set or contaminate the runtime environment
- remove logs, caches, experiment results, or intermediate outputs
- consume GPU, CPU, disk, or network resources incorrectly
- interfere with other services on the same machine, or even make a server unstable

If you run it directly on a high-privilege host, production machine, shared development server, or a system holding important data, the risk increases substantially.

### 2.2 Fabricated Results, Wrong Conclusions, And Research Risk

DeepScientist is model-driven. It does not guarantee truth.

It may:

- fabricate metrics, logs, tables, or experiment results
- invent citations, prior work summaries, or baseline comparisons
- drift away from the intended task or evaluation protocol
- produce analyses that sound plausible but are not reproducible
- write conclusions that are too strong for the available evidence

Any experiment result, paper text, chart, citation, conclusion, or reviewer response must be reviewed by a human before you treat it as trustworthy.

### 2.3 Data Loss, Corruption, And Irreversible Changes

Even without obvious malicious behavior, automation can still produce irreversible damage.

Examples:

- quest files get overwritten
- uncommitted local edits get polluted
- auto-generated files mix into final result directories
- a bad script corrupts datasets or experiment folders at scale
- an external connector receives outputs that should not have been sent

If your data, projects, or paper drafts are not backed up, this kind of damage may be difficult to recover from.

### 2.4 Secret, Credential, And Privacy Leakage

DeepScientist may touch sensitive material such as:

- API keys
- environment variables
- private repository locations
- research data
- connector tokens
- WeChat, QQ, Lingzhu, or other external account bindings

If you:

- expose the site publicly
- share the DeepScientist page casually
- allow untrusted users into the runtime environment
- send config files, logs, screenshots, or quest files that contain sensitive material

you may leak:

- model credentials
- connector identities
- WeChat or QQ messaging authority
- project data, experiment material, or private content

Once connectors are bound, the risk is no longer only "can someone open the page?" but also "can someone misuse the linked external account?"

### 2.5 Public Exposure And Unauthorized Access

If you bind DeepScientist to `0.0.0.0`, a public IP, a reverse proxy, a tunnel, or a public domain, you are exposing an automation-capable system to the outside.

That can lead to:

- unauthorized access
- session probing or replay
- misuse of connector callback or polling contexts
- external visibility into project pages, settings pages, or logs
- accidental disclosure of internal paths, ports, or service topology

If WeChat, QQ, or other connectors are also bound, the impact is larger.

Unless you fully understand the consequences, do not casually share the site address and do not expose the operational UI to uncontrolled users.

### 2.6 Third-Party Platform And Account Compliance

DeepScientist can integrate with QQ, WeChat, Lingzhu, and other external platforms.

You are responsible for:

- third-party platform terms-of-service risk
- account suspension, rate-limit, restriction, or audit risk
- abuse complaints caused by automated outbound messages
- privacy and compliance issues caused by relaying data or files through those platforms

The project maintainers do not guarantee that your usage will satisfy local law, internal policy, or platform rules.

### 2.7 Malicious Inputs, Prompt Injection, And Supply-Chain Risk

DeepScientist can read:

- repositories
- papers
- web pages
- issues, PRs, or READMEs
- uploaded attachments
- connector messages and files

Any of those can contain:

- malicious commands
- prompt injection
- misleading instructions
- fake benchmarks
- dependency installation steps with backdoors

If the model follows those instructions, the resulting behavior can become much more dangerous.

### 2.8 Resource, Cost, And Abuse Risk

DeepScientist may run for a long time, call models repeatedly, download dependencies, execute experiments, and produce large numbers of files.

You are responsible for:

- API cost growth
- GPU or CPU occupation
- disk growth caused by logs, caches, artifacts, or datasets
- long-running load, overheating, or service contention

## 3. Minimum Safety Practices Strongly Recommended

If you plan to use DeepScientist seriously, at least do the following.

### 3.1 Prefer Docker Or Another Isolated Environment

Strongly prefer running DeepScientist inside Docker, a virtual machine, or an equivalent isolation boundary instead of running it directly on a privileged host.

The goal is simple:

- reduce filesystem blast radius
- reduce process privilege
- reduce network exposure
- reduce recovery cost when something goes wrong

### 3.2 Always Use A Non-Root Account

Strong recommendation:

- run DeepScientist under a dedicated non-root user
- do not start it as `root`
- do not give it default write access to the whole machine
- do not let it touch sensitive host directories by default

If you must run it on a server, least privilege matters even more.

### 3.3 Do Not Run It Directly On Production Or Critical Machines

Avoid running DeepScientist directly on:

- production database hosts
- live business servers
- control machines that store core source code and secrets
- shared bastion hosts
- desktops that hold important personal or commercial data

### 3.4 Do Not Casually Share The Site Address Or Public Entry

Unless you already have proper access control in place, do not:

- post the DeepScientist URL in public groups
- map a `0.0.0.0`-bound port directly to the public internet
- publish an unauthenticated reverse-proxy address
- give other people direct operational access to a runtime that already has connectors bound

This is not only a page-viewing risk. It is also a credential and connector-authority leakage risk.

### 3.5 Minimize Credential And Connector Privilege

Recommended:

- use separate test accounts for QQ, WeChat, or Lingzhu bindings
- avoid exposing your highest-value primary accounts to experimental runtimes
- do not keep every token in a single shared home directory
- rotate keys and connector tokens regularly
- keep outbound authority as narrow as possible

### 3.6 Review Every Important Result Manually

Do not directly trust:

- experiment metrics
- charts
- paper sections
- related work summaries
- citation lists
- ablation claims
- statuses like "reproduced successfully"

The correct approach is to:

- inspect raw files
- inspect runtime logs
- inspect scripts and configs
- rerun key experiments
- spot-check citations and numbers

### 3.7 Prepare Backup And Rollback

At minimum:

- put important quests under Git
- back up `~/DeepScientist`
- snapshot important data directories
- separate production data from experimental data

## 4. Short Version

The shortest safe summary is:

1. DeepScientist is released under Apache 2.0.
2. The project authors and maintainers are not responsible for any consequence caused by your use of DeepScientist.
3. It may damage a server, delete files, leak credentials, send wrong external messages, or fabricate results.
4. Strongly prefer Docker or an equivalent isolated environment, and always run under a non-root account.
5. Do not casually share the site address, and do not expose a runtime with bound WeChat, QQ, or other connectors to uncontrolled users.
