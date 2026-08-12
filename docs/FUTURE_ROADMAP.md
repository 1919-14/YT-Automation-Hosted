# 🚀 Night Loom — Future Sprint Roadmap & Brainstorming Ideas

This document logs architectural concepts, feature proposals, and optimization ideas brainstormed for future development sprints.

---

## 📌 Sprint Proposal 1: Dynamic Visual Animation Engine

### Goal
Transform static SDXL image slides into dynamic, animated 3D video scenes matching viral high-retention Shorts.

### Implementation Features
- **Phase 1 — FFmpeg Dynamic Motion Engine (0 extra VRAM, instant render)**:
  - Organic smooth 3D Ken Burns camera zoom-in / zoom-out on subject focus points.
  - Subtle horizontal parallax pan & tilt filters.
  - Atmospheric lighting pulses (eye glow, phone screen flicker).
  - Dynamic directional push-zoom and glitch transitions between scenes.
- **Phase 2 — Local AI Image-to-Video (Stable Video Diffusion / AnimateDiff)**:
  - Optional `--ai-video` flag in `visuals_stage.py`.
  - Generates 3-second 25fps physical motion clips (blinking, breathing, hair movement, drifting fog) locally on 6GB VRAM GPUs using FP8 quantization.

---

## 🎨 Sprint Proposal 2: Graphic Novel & Dark Comic Art Style Engine

### Goal
Shift the visual aesthetic from general photorealism to a high-CTR **Dark Graphic Novel / Comic Book Thriller** aesthetic.

### Implementation Features
- **Prompt Token Upgrade in `visuals_planner.py`**:
  - Add stylized graphic novel tokens: `dark graphic novel comic art style, detailed line art, dramatic chiaroscuro lighting, expressive intense facial expression, eerie atmospheric shading`.
- **Thumbnail Aesthetic Sync**:
  - High-contrast visual subject with bold outlines and vibrant focal highlights (red/yellow/white) for maximum mobile feed CTR.

---

## 🧠 Sprint Proposal 3: Closed-Loop Self-Learning & Self-Growing Engine

### Goal
Replace random video creation with an **Autonomous Channel Manager** that analyzes real YouTube Analytics data to continuously increase retention, CTR, views, and subscriber growth.

### Implementation Features
- **1. YouTube Analytics Collector (`scripts/youtube_analytics.py`)**:
  - Automatically queries `youtubeAnalytics.v2` API 48 hours post-upload.
  - Tracks: CTR %, Average Percentage Viewed (APV), Audience Drop-off Timestamps (e.g. second at which viewers swiped away), Subscriber conversion per 1,000 views.
- **2. AI Performance Critic / Evaluator**:
  - Feeds analytics JSON back to LLM to diagnose *why* a video succeeded or failed.
  - Generates actionable prompt adjustments for future scripts and thumbnails.
- **3. Dynamic Channel Genome Matrix**:
  - Stores winning weights in SQLite DB (`channel_genome` table):
    - Story Category Weights (e.g. Mystery Thrillers vs Survival vs Tech Myths).
    - Script Hook Pacing & Tension level.
    - Visual cut frequency (e.g. 2.2s per cut vs 4.0s per cut).
- **4. 80/20 Multi-Armed Bandit Strategy**:
  - **80% Exploitation**: Automatically generates videos using top-performing proven formulas.
  - **20% Exploration**: Tests new creative experiments (new hook style, voice pitch, thumbnail layout).

---

## 🔊 Sprint Proposal 4: Advanced Audio & Multi-Speaker Experience

### Goal
Enhance audio immersion and emotional impact.

### Implementation Features
- **Multi-Speaker Narrations**: Dual-voice storytelling (narrator + character dialogue).
- **Automated Sound FX Triggers**: Synced thunder, heartbeats, glitches, or door creaks based on script emotion tags.
- **Dynamic Background Music Ducking**: Auto-adjusts background track volume depending on speech intensity.

---

## ⚡ Sprint Proposal 5: Gamified Economic Survival Engine (Autonomous Credit Economy)

### Goal
Introduce a **Credit-Based Survival Mechanism** where the AI pipeline operates with a virtual "wallet/bank account". Every operation consumes credits (costing resources/GPU/APIs), and the AI must earn credits through real YouTube views, watch time, likes, and subscribers to survive.

### Mechanics & Architecture

#### 1. Credit Costs (Expenses / Debit Ledger)
- **Script Generation (LLM API Call)**: `-15 Credits`
- **SDXL Shot Rendering (GPU Compute)**: `-10 Credits / image` (or `-2 Credits` if cached/reused)
- **SadTalker / Wav2Lip Avatar Rendering**: `-25 Credits / video`
- **YouTube API Upload Call**: `-5 Credits`
- **GPU Wattage / Runtime Minute**: `-1 Credit / min`

#### 2. Credit Rewards (Earnings / Income Ledger)
- **Views**: `+1 Credit / 100 views` (or `+10 Credits / 1,000 Shorts views`)
- **Watch Time**: `+5 Credits / watch hour`
- **Subscribers**: `+20 Credits / new subscriber`
- **Likes & Engagement**: `+2 Credits / 100 likes`
- **Monetization / AdSense Revenue**: `+100 Credits / $1 revenue`

#### 3. Dynamic Behavioral Survival Modes
Depending on its credit balance stored in `wallet` DB table, the AI shifts its creative behavior:
- **High Budget Mode (> 2,000 Credits)**:
  - Generates ambitious 10-minute long-form stories, 4K visual art, full AI video motion, dual-voice narration. Takes creative risks and tests new experimental genres.
- **Moderate Budget Mode (500 – 2,000 Credits)**:
  - Balances production costs with proven high-CTR templates. Uses standard 60-second Shorts format with optimized shot counts.
- **Survival Crisis Mode (< 200 Credits)**:
  - Enters emergency frugal survival mode: switches to ultra-lean 15-second Shorts, reuses existing background assets, aggressively crafts viral mystery hooks to gain emergency views, and minimizes GPU compute time.
- **Bankruptcy / Hibernation Mode (0 Credits)**:
  - Halts automated production pipeline until external credit recharge or low-cost analytical tasks earn sufficient credits.

---

## 🤖 Sprint Proposal 6: Fully Autonomous AI Brain & Web Intelligence Agent

### Goal
Transform the YouTube Automation pipeline into a **24/7 Fully Autonomous Intelligent Agent (An Executive AI Brain)** that independently decides *what* content to make, *when* to make it, *researches real-world trending data*, and operates self-sufficiently without human intervention.

### Master Architecture

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      🧠 AUTONOMOUS AGENT BRAIN                         │
 │                                                                        │
 │  ┌────────────────────────┐         ┌───────────────────────────────┐  │
 │  │ 🕵️ Web Research Agent   │         │ 📊 YouTube Analytics Agent    │  │
 │  │ (Google/Trends/Reddit) │         │ (CTR, Retention, Views, Subs) │  │
 │  └───────────┬────────────┘         └───────────────┬───────────────┘  │
 │              │                                      │                  │
 │              └──────────────────┬───────────────────┘                  │
 │                                 ▼                                      │
 │                  ┌──────────────────────────────┐                      │
 │                  │ 🤖 Executive Decision Engine │                      │
 │                  │  - Evaluate Credit Wallet    │                      │
 │                  │  - Select Topic & Format     │                      │
 │                  │  - Schedule Optimal Upload   │                      │
 │                  └──────────────┬───────────────┘                      │
 └─────────────────────────────────┼──────────────────────────────────────┘
                                   │
                                   ▼
          ┌──────────────────────────────────────────────────┐
          │  🎬 Automated Video Production Pipeline          │
          │  (Script → Voice → Visuals → Render → AutoUpload)│
          └──────────────────────────────────────────────────┘
```

### Key Modules

#### 1. 🕵️ Web Research & Trend Discovery Engine (`scripts/research_agent.py`)
- **Live Data Scraping**: Connects to Google Trends API, Reddit (r/UnsolvedMysteries, r/AskReddit, r/Science), Twitter/X trends, and YouTube Search APIs.
- **Trend Spotting**: Identifies rapidly spiking search terms and emerging viral stories before they peak.
- **Fact Verification & Synthesis**: Gathers real-world facts, dates, and historical context to ensure scripts are accurate, engaging, and rich in detail.

#### 2. 🕒 Autonomous Executive Scheduler & Decision Engine (`scripts/executive_brain.py`)
- **24/7 Background Heartbeat**: Runs as a lightweight system service daemon.
- **Optimal Upload Scheduling**: Analyzes audience peak activity times from YouTube Analytics to schedule uploads at exact high-traffic hours.
- **Self-Directed Decision Making**:
  - Checks Credit Wallet balance (Proposal 5).
  - Evaluates past retention learnings (Proposal 3).
  - Decides whether to produce a Short (fast, viral) or a Long-Form deep dive (high revenue).
  - Automatically triggers the full video production pipeline when optimal conditions are met.

#### 3. 🛡️ Risk Management & Safety Limits
- **Daily Budget Cap**: Enforces maximum API/GPU usage limits per 24-hour cycle.
- **Copyright & Safety Filter**: Scans scripts and generated images for policy violations or copyright risks before publishing.

---

## 🔎 Sprint Proposal 7: Dedicated Web Research & Fact Synthesis Agent

### Goal
Build a dedicated research sub-system (`scripts/research_agent.py`) capable of real-time web search, trend discovery, and fact verification to feed high-authority accurate data into all channel sub-projects.

### Implementation Features
- **Real-Time Search APIs Integration**: DuckDuckGo, Tavily, SerpAPI, NewsAPI, and Google Trends.
- **Fact Verification Engine**: Cross-references claims across multiple reputable sources before feeding narrative text to `script_generator.py`.
- **Entity & Metric Extraction**: Extracts exact names, dates, quotes, numbers, and timeline events for educational & news channels.

---

## 🎭 Sprint Proposal 8: Specialized Channel Sub-Projects & Multi-Niche Engine

### Goal
Expand the single-channel architecture into a **Multi-Channel Empire Platform** supporting dedicated sub-projects tailored for specific viral niches.

### 1. Sub-Project A: 💻 "CodeMemes & Dev Humor" Channel (`projects/codememes/`)
- **Target Audience**: Programmers, Software Engineers, Tech Enthusiasts.
- **Content Style**: Fast-paced 15–30s Shorts featuring developer humor (Junior vs Senior Dev, JavaScript quirks, C++ memory leaks, AI taking coding jobs).
- **Automated Pipeline Features**:
  - Meme Scraper & Generator: Scrapes trending dev humor from Reddit (`r/programmerhumor`, `r/DevOpsMemes`, `r/CodingMemes`) and generates custom visual meme formats.
  - Sound Effects Triggering: Auto-inserts iconic comedy sound effects (Vine boom, record scratch, Minecraft hurt sound, Windows error chime).
  - Animated Code Overlays: Renders syntax-highlighted code blocks with dynamic typing animations.

### 2. Sub-Project B: 📰 "24-Hour Daily News Digest" Channel (`projects/dailynews/`)
- **Target Audience**: General Public, Tech & Science Followers, Daily News Seekers.
- **Content Style**: Concise 60-second daily recap Shorts and 3–5 minute long-form videos summarizing the top breaking stories of the past 24 hours.
- **Automated Pipeline Features**:
  - 24-Hour News Harvester: Runs automatically every evening at 6:00 PM, pulling top headline feeds (AI/Tech news, Science breakthroughs, Global events).
  - Ticker & Headline Graphics: Generates a news broadcast overlay with a bottom scrolling ticker, breaking news badges, and side-by-side topic cards.
  - Automated Scheduling: Auto-publishes daily news Shorts before morning commuting hours.

---

## 📱 Sprint Proposal 9: Telegram Command Center & Multi-Channel Remote Controller

### Goal
Build a dedicated Telegram Bot (`scripts/telegram_bot.py`) that acts as a mobile control center for your phone. Allows 1-tap remote execution of video pipelines across multiple dedicated YouTube channels with live stage progress updates and instant error notifications.

### Master Telegram Bot Features

#### 1. 🎛️ Interactive Command Menu (Inline Keyboards)
Tapping `/menu` on your phone presents quick action buttons:
- 🎬 `[NightLoom Short]` | 📜 `[NightLoom Long Video]`
- 💻 `[Generate Dev Meme]` | 📰 `[Daily News Digest]`
- 📊 `[Channel Analytics]` | 💳 `[Wallet Balance & Health]`

#### 2. 🔀 Multi-Channel Routing Engine (`scripts/channel_router.py`)
Single bot controls multiple distinct YouTube channels with separate OAuth credentials & brand templates:
- **Channel 1**: `Night Loom` (Mysteries & Storyteller Channel)
- **Channel 2**: `CodeMemes` (Developer & Tech Humor Channel)
- **Channel 3**: `Daily News Brief` (24-Hour Automated News Channel)

#### 3. 📲 Real-Time Stage Progress Push Notifications
Sends live status cards to your phone as each pipeline stage executes:
- 🟢 `[Stage 1/7] Script Generated: "The Mirror in My Hallway..."`
- 🗣️ `[Stage 2/7] Voice Narration & Subtitles Ready`
- 🎨 `[Stage 3/7] SDXL Visuals Rendered (8/8)`
- 🎬 `[Stage 5/7] Video Composited: 1080x1920 ready`
- 🎉 `[Stage 7/7] UPLOAD SUCCESSFUL! Watch: https://youtu.be/...`

#### 4. 🚨 Remote Error Alerts & 1-Tap Recovery
- If any stage fails, the bot sends an instant alert:
  - `🚨 [ALERT] Stage 4 Failed on Video 12: CUDA Memory Error.`
  - Includes interactive buttons: `[🔁 Retry Stage]` | `[⏭️ Skip Stage]` | `[🛑 Abort Job]`

---

## 📱 Sprint Proposal 9: Telegram Command Center Bot & Multi-Channel Platform

### Goal
Build a dedicated **Telegram Control Bot (`scripts/telegram_bot.py`)** allowing full remote control of the YouTube Automation platform from your smartphone, with multi-channel routing (Night Loom Storyteller, CodeMemes, Daily News Digest).

### Master Control Architecture

```
                       📱 Telegram Smartphone App
                                   │
                                   ▼
                       🤖 Telegram Command Bot
                    (python-telegram-bot / Webhooks)
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
  🎬 Night Loom Channel   💻 CodeMemes Channel   📰 Daily News Channel
  (Storytelling Shorts    (Dev Humor Shorts &    (24-Hour News Recaps
   & 16:9 Long Videos)     Meme Compilations)     & Broadcast Overlays)
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   ▼
                    📊 Multi-OAuth Token Router
            (token_nightloom.json, token_codememes.json, etc.)
```

### Key Capabilities & Workflow

#### 1. 🎛️ Interactive Inline Keyboard Menu (Telegram UI)
When you type `/start` or `/menu` in Telegram, an interactive button menu appears on your phone:
- **Night Loom Storyteller Channel**:
  - `[ 🎬 Generate Shorts (9:16) ]`
  - `[ 📺 Generate Long-Form (16:9) ]`
  - `[ ✍️ Custom Story Prompt ]`
- **CodeMemes Channel**:
  - `[ 💻 Generate Dev Meme Short ]`
  - `[ 🤖 Scrape Reddit Hot Memes ]`
- **Daily News Channel**:
  - `[ 📰 Generate 24h News Digest ]`
  - `[ 🔍 Custom News Query ]`
- **System & Analytics**:
  - `[ 💳 Wallet & Credit Balance ]`
  - `[ 📈 Recent Video Stats & Views ]`

#### 2. 🔑 Multi-Channel YouTube OAuth Router (`scripts/channel_router.py`)
- Manages separate OAuth tokens per channel:
  - `channels/nightloom/token.json`
  - `channels/codememes/token.json`
  - `channels/dailynews/token.json`
- Passing `--channel <name>` to the pipeline automatically selects the matching OAuth credentials, branding templates, logos, and target YouTube channel.

#### 3. 📲 Real-Time Push Notifications & Live Previews
- **Stage Progress Updates**: Telegram sends live progress messages (e.g. `[Voice 100%] → [SDXL Visuals 100%] → [Rendering...]`).
- **Upload Alert**: When YouTube upload finishes, Telegram sends a push notification directly to your phone containing:
  - 🔗 **Direct YouTube Watch Link** (`https://youtu.be/...`)
  - 🖼️ **Thumbnail Preview Image**
  - 📊 **SEO Title & Tag summary**
