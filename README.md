# Esendex skills for AI agents

Skills that teach an AI agent to use the Esendex SMS platform: send and schedule messages,
track what was delivered, manage contacts and consent, and connect over SMPP.

They follow the Agent Skills format, so Claude, Gemini and ChatGPT load them directly, and
any other agent can read them as plain Markdown. Ask in plain English, "text my
customers on Monday" or "did that text go out?", and the agent works out which API calls to
make.

## What's in the kit

| Skill | What it does |
| --- | --- |
| `esendex-setup-account` | Connects to your account: authentication, rate limits and your prepay balance. The other skills build on this one. |
| `esendex-send-message` | Sends messages now, at a set time, or spread over hours or days. Handles templates and personalisation, and estimates the cost before sending. |
| `esendex-track-delivery` | Reports what happened to a send: delivery reports, failure reasons, replies, link clicks, and webhooks for live updates. |
| `esendex-manage-contacts` | Imports and organises contacts, builds groups, and manages your opt-out list. |
| `esendex-connect-smpp` | Connects over SMPP v3.4, for an existing SMPP client or platform. |

## Install

One folder per skill, each with a `SKILL.md` describing what it is for. Anthropic, Google and
OpenAI all load that format natively, so for most agents installing means cloning the repository
and copying the folders into a directory.

```bash
git clone --depth 1 https://github.com/esendex/esendex-skills.git
```

The five skill folders are in `esendex-skills/esendex-developer-kit/skills/`. Copy whole
folders, not single files: each `SKILL.md` links to the reference files beside it by relative
path, so a lone `SKILL.md` loses most of its detail.

The directory paths below follow each vendor's current conventions, which can change. If a
path does not work, check that vendor's documentation.

### Anthropic - Claude

Claude Code reads `.claude/skills/` in a project and `~/.claude/skills/` everywhere.

```bash
mkdir -p ~/.claude/skills
cp -r esendex-skills/esendex-developer-kit/skills/* ~/.claude/skills/
```

Or install the packaged plugin, which also tracks updates. `esendex-skills` is this
repository, `esendex-developer-kit` the plugin it publishes, and `esendex-marketplace` the
catalogue it is listed in.

```
/plugin marketplace add esendex/esendex-skills
/plugin install esendex-developer-kit@esendex-marketplace
```

In the Claude apps, zip a skill folder and upload it under Settings, Capabilities, Skills. On
the Agent SDK, point your agent's skills directory at `esendex-developer-kit/skills/`.

### Google - Gemini

Gemini CLI reads `.gemini/skills/` in a project and `~/.gemini/skills/` everywhere.

```bash
mkdir -p ~/.gemini/skills
cp -r esendex-skills/esendex-developer-kit/skills/* ~/.gemini/skills/
```

`gemini skills install` will also take a repository URL or a local `.skill` package. The first
time a skill activates, Gemini names it and the directory it is about to read, and waits for
you to approve.

### OpenAI - Codex and ChatGPT

Codex reads `.agents/skills/` at a repository root and `~/.agents/skills/` everywhere, in the
CLI and the IDE extension alike. Run `/skills` to list them, or type `$` to call one by name.

```bash
mkdir -p ~/.agents/skills
cp -r esendex-skills/esendex-developer-kit/skills/* ~/.agents/skills/
```

In ChatGPT, zip a skill folder so the folder itself is the top-level entry, then go to
Plugins, Skills, Create, Upload from your computer. Skills are a workspace feature there, so
you need a Business, Enterprise, Healthcare or Edu account and a workspace that allows them.

```bash
cd esendex-skills/esendex-developer-kit/skills
zip -r esendex-send-message.zip esendex-send-message
```

On Enterprise and Edu, an administrator decides which roles may create, use and upload skills,
so if the menu is missing or an upload is refused, ask your administrator for that permission.

On the API, upload a skill and pass its `skill_id` to the Responses API, or list the directory
in `capability_directories` on the Agents API.

### One folder for several agents

The `.agents/skills/` location in the Codex instructions above is a shared convention, not an
OpenAI one. Gemini CLI reads it as an alias for `.gemini/skills/`, and Cursor and GitHub
Copilot read it too, so if you use more than one of those, install once there instead of once
per tool.

Claude Code is the exception. It reads its own location only, so keep the `.claude/skills/`
copy as well.

### Any other agent

For an agent with no skills directory, or where you would rather keep the skills in the
project, copy the folders in and tell it where they are.

```bash
cp -r esendex-skills/esendex-developer-kit/skills .esendex-skills
```

Then paste this into whichever file it reads for project instructions - `.windsurf/rules/esendex.md`
for Windsurf, and so on:

```markdown
## Esendex SMS

Skills for the Esendex SMS API are in `.esendex-skills/`. Before writing any Esendex code,
read the `SKILL.md` whose description matches the task, and follow the files it links to.
```

### After that

Once installed, you do not need to name a skill. Each one carries a description of when it
applies, and your agent uses that to choose. Ask for the task, for example "text everyone who
hasn't collected their order yet", and the agent loads the matching skill. If nothing happens,
check the paths above against your tool's documentation.

## Credentials

Whichever agent you use, it reads two environment variables:

```bash
export ESENDEX_API_KEY='...'
export ESENDEX_ACCOUNT_REFERENCE='EXUK0000000'
```

You need an Esendex account with both Admin and Developer rights. Without both, the Developer
Tools menu does not appear in the portal; ask the account owner to grant them.

Your API key is in the [Esendex portal](https://app.esendex.co.uk/) under Developer Tools. Set
an expiry date, and use a separate key for each developer or system. The portal address and
the `EXUK` reference format shown here are Esendex UK&I; other territories have their own
portal and their own account references, and one key does not span them.

## Before you send

When the API accepts a message, the message is queued for delivery. The delivery status
arrives later, so the skills tell the agent to report a queued send as queued and to check the
delivery state separately.

Check your opt-outs before a bulk send. Under PECR and GDPR in the UK and EU, and the TCPA in
the US, messaging someone who has opted out can expose the account holder to regulatory
penalties. The skills tell the agent to check your suppression list before a campaign goes out,
and to report how many recipients it removed.

The skills guide an agent's behaviour but cannot guarantee it. Treat the checks above as
working practice, and keep your own controls on anything that sends to real recipients.

## Terms

Use of the Esendex platform is governed by the Commify
[Terms of Service](https://enhancedsupport.esendex.co.uk/terms-of-service/), along with the
[Acceptable Use Policy](https://enhancedsupport.esendex.co.uk/acceptable-use-policy/),
[Data Processing Agreement](https://enhancedsupport.esendex.co.uk/data-processing-agreement/) and
[Service Level Agreement](https://enhancedsupport.esendex.co.uk/service-level-agreement/).

Each skill includes a summary of the terms that apply to it. Where a summary and the published
terms differ, the published terms apply. Nothing in this repository is legal advice.

## Support

- API documentation: [developer.esendex.co.uk](https://developer.esendex.co.uk/)
- Help with your account: [enhancedsupport.esendex.co.uk](https://enhancedsupport.esendex.co.uk/)
- Problems with these skills: open an issue on this repository

## Maintaining

Each skill ships its own copy of `esendex_client.py`, so it works when installed on its own.
The source is `src/esendex_client.py`: edit that, never a copy, then run
`python3 sync_client.py` to update the five copies. `python3 sync_client.py --check` fails if
any copy has drifted; run it, and `python3 src/esendex_client.py` for the self-test, before
opening a pull request.

## Licence

Copyright 2026 Commify UK Ltd. Apache 2.0 - see [LICENSE](LICENSE).
