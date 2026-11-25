"""Build the standalone final deck from the prior design, notes and real captures.

Standard library only. Run capture_demo.py first to refresh the image assets.
The earlier progress deck is read, never modified.
"""
import base64
from html import escape
import mimetypes
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parent
PREVIOUS = ROOT.parent / 'seminar-progress'
TIMES = [15, 25, 35, 40, 25, 45, 30, 30, 40, 40, 25]
LABELS = ['From calendar to deployed product', 'A brief recap', 'Complete recurring workflows',
          'Availability is now calculated', 'Check before accepting a shift', 'Ask your schedule', 'Reliability and verification',
          'A working Azure deployment', 'From push to deployment', 'Social signup and demo access', 'Delivered outcome']

STYLES = r'''
/* === FINAL DECK: THE SAME OPEN HOURS PALETTE, A NEW SIX-MINUTE STORY === */
.final{padding:78px 90px}.final h2{font-size:82px;line-height:1.06;letter-spacing:-3.6px;margin-top:30px;font-weight:600}
.final h3{font-size:38px;line-height:1.18;letter-spacing:-1px}.final p{font-size:32px;line-height:1.45}
.final .eyebrow{font-size:22px}.final .slide-footer{bottom:44px;font-size:20px}
.subtitle{color:var(--muted);margin-top:25px;max-width:1400px}.accent{color:#98633c}
.tag{display:inline-block;border:1px solid var(--line);padding:10px 18px;font-size:23px;letter-spacing:.5px}
.tag.live{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.live-dot{display:inline-block;width:11px;height:11px;border-radius:50%;background:#bcd68e;margin-right:12px;vertical-align:middle}
.section-line{border-top:2px solid var(--line);padding-top:24px}.final a{color:inherit;text-decoration-thickness:1px;text-underline-offset:6px}
.note-line{position:absolute;left:90px;right:90px;bottom:124px;font-size:27px!important;color:var(--muted)}
/* === OPENING: RECOGNIZABLE TITLE AND THREE DELIVERED OUTCOMES === */
.final-cover{background:linear-gradient(90deg,var(--paper) 0 66%,var(--ink) 66%)}
.final-cover h1{font-size:150px;line-height:.99;letter-spacing:-7px;margin:95px 0 35px;width:1080px}
.final-cover .cover-subtitle{font-size:41px;max-width:1080px}.final-cover .slide-footer{right:730px}
.outcome-rail{position:absolute;left:1340px;top:213px;width:420px;color:var(--paper)}
.outcome-rail .mini-label{font-size:20px;color:#bdcfc0;margin-bottom:47px}
.outcome-rail>div{padding:26px 0;border-top:1px solid #658575}.outcome-rail strong{font-size:47px;font-weight:500}
.outcome-rail p{font-size:26px;color:#cad7cd;margin-top:10px}.cover-status{margin-top:37px}
/* === RECAP: THREE CLEAR BEFORE/AFTER ROWS === */
.recap-grid{display:grid;grid-template-columns:1fr 1fr;gap:90px;margin-top:65px}
.recap-panel{border-top:2px solid var(--line);padding-top:24px}.recap-panel.now{border-top-color:var(--ink)}
.recap-panel .mini-label{font-size:24px;margin-bottom:30px}.recap-panel ul{list-style:none;margin:0;padding:0}
.recap-panel li{font-size:34px;line-height:1.35;padding:21px 0;border-bottom:1px solid var(--line)}
.recap-panel.now li{color:var(--ink)}.recap-panel.before li{color:var(--muted)}
/* === PRODUCT EVIDENCE: REAL CAPTURES AND LARGE EXPLANATORY COPY === */
.two-column{display:grid;grid-template-columns:650px 1000px;gap:80px;margin-top:55px;align-items:start}
.body-copy{display:flex;flex-direction:column;gap:29px}.body-copy p{color:var(--muted)}
.body-copy h3{margin-bottom:12px}.evidence{margin:0;min-width:0}.browser-label{background:#e8e9df;border:1px solid var(--line);border-bottom:0;padding:14px 22px;font-size:21px;color:var(--muted)}
.browser-label:before{content:'● ● ●';font-size:13px;letter-spacing:3px;margin-right:24px;color:#9aa99a}
.evidence img{display:block;width:100%;border:1px solid var(--line);background:white;object-fit:cover;object-position:top}
.evidence figcaption{font-size:20px;color:var(--muted);margin-top:13px;line-height:1.4}
.recurring-image{height:540px}.revision{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
.revision>div{padding:20px;background:#e8eadd}.revision strong{display:block;font-size:38px;margin-top:9px}.revision span{font-size:23px;color:var(--muted)}
.callout{border-left:5px solid var(--warm);padding-left:24px;font-size:30px!important}
/* === AVAILABILITY: THE ORIGINAL EXAMPLE, NOW WITH AN IMPLEMENTED RESULT === */
.availability-layout{display:grid;grid-template-columns:1010px 650px;gap:70px;margin-top:55px}
.demo-axis{display:flex;justify-content:space-between;font-size:23px;color:var(--muted);margin:13px -8px 28px}
.lane-label{font-size:26px;margin-bottom:14px;display:flex;justify-content:space-between}
.lane-label span{color:var(--muted)}.willing-lane{height:34px;background:#d5ddcf;border:1px solid #a2b399}
.occupied-lane,.free-lane{position:relative;height:92px;margin-bottom:30px}
.occupied-lane>div{position:absolute;top:0;height:100%;padding:15px 18px;font-size:26px;line-height:1.15;width:16.6667%}
.occupied-lane small{font-size:20px}.occupied-lane .class{left:16.6667%;background:#d5ddeb;border-left:4px solid #6474a4}
.occupied-lane .study{left:33.3333%;background:#e8cbaa;border-left:4px solid #b4773f}
.free-lane>div{position:absolute;height:76px;display:flex;align-items:center;justify-content:center;background:var(--ink);color:var(--paper);font-size:26px}
.free-lane .first{width:16.6667%}.free-lane .second{left:50%;width:50%}
.share-answer{background:var(--ink);color:var(--paper);padding:35px 38px}.share-answer .mini-label{font-size:21px;color:#c9d8c8}
.share-answer strong{display:block;font-size:46px;line-height:1.55;margin-top:19px;font-weight:500}.share-answer p{font-size:25px;margin-top:22px;color:#d7e0d4}
.availability-proof{margin:22px 0 0}.availability-proof img{width:650px;max-height:145px;object-fit:contain;object-position:left top;border:1px solid var(--line);background:#fff}
.availability-proof figcaption{font-size:19px;color:var(--muted);margin-top:8px}
/* === SHIFT CHECK: DECISION BEFORE SAVING, NOT A NEW COMMITMENT === */
.shift-layout{grid-template-columns:700px 950px}.shift-evidence img{height:580px;object-fit:contain;background:white}
.decision{padding:22px 0;border-bottom:1px solid var(--line)}.decision strong{display:block;font-size:35px;margin-bottom:9px}
.decision p{font-size:28px}.decision .dot{width:13px;height:13px;display:inline-block;border-radius:50%;margin-right:13px;background:#a45c3e}
.decision:first-child .dot{background:#38654e}.decision:last-child .dot{background:#b88935}
/* === RELIABILITY: A VERIFIED COUNT WITH THE BEHAVIOR BEHIND IT === */
.reliability-layout{display:grid;grid-template-columns:690px 890px;gap:130px;margin-top:45px}
.test-number{font-size:230px;line-height:1.2;letter-spacing:-13px;font-weight:600;margin:5px 0 16px}
.test-number-label{font-size:35px!important}.previous-count{margin-top:32px;font-size:26px!important;color:var(--muted)}
.verified-grid{display:grid;grid-template-columns:1fr 1fr;gap:28px 38px;margin-top:26px}
.verified-grid>div{border-top:2px solid var(--line);padding-top:20px}.verified-grid h3{font-size:33px}.verified-grid p{font-size:25px;color:var(--muted);margin-top:12px}
.rehearsal-strip{background:#e3e8da;padding:25px 28px;margin-top:35px;font-size:28px}
/* === CLOUD: ONE VM, THREE CONTAINERS, PERSISTENT STORAGE === */
.url-ribbon{margin-top:40px;font-size:36px;font-weight:500;letter-spacing:-.8px}
.cloud-outline{margin-top:40px;border:2px solid var(--line);padding:28px 35px 36px;position:relative}
.cloud-label{font-size:23px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:29px}
.cloud-nodes{display:grid;grid-template-columns:1fr 55px 1fr 55px 1fr;gap:20px;align-items:center}
.cloud-node{padding:36px 30px;background:#e4e8dc;min-height:220px}.cloud-node.primary{background:var(--ink);color:var(--paper)}
.cloud-node h3{font-size:40px}.cloud-node p{font-size:28px;margin-top:17px}.cloud-node .mini-label{font-size:19px;margin-bottom:17px;color:var(--muted)}
.cloud-node.primary .mini-label{color:#d0dbc7}.cloud-arrow{text-align:center;font-size:40px;color:var(--muted)}
.cloud-notes{display:grid;grid-template-columns:1fr 1fr 1fr;gap:40px;margin-top:35px}.cloud-notes p{font-size:28px;color:var(--muted)}
/* === CI/CD: FOLLOW THE CODE TO A VERIFIED DEPLOYMENT === */
.pipeline{display:grid;grid-template-columns:260px 55px 340px 55px 340px 55px 340px;gap:18px;align-items:center;margin-top:75px}
.pipeline-node{border-top:4px solid var(--ink);padding:27px 20px;background:#e5e9dd;min-height:228px}
.pipeline-node .step{margin-bottom:25px;font-size:22px}.pipeline-node h3{font-size:36px}.pipeline-node p{font-size:25px;color:var(--muted);margin-top:14px}
.pipeline-node.last{background:var(--ink);color:var(--paper)}.pipeline-node.last p,.pipeline-node.last .step{color:#d2dfce}
.pipeline-arrow{font-size:39px;color:var(--muted);text-align:center}
.pipeline-proof{display:flex;justify-content:space-between;align-items:center;margin-top:65px;padding:25px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.pipeline-proof strong{font-size:32px;font-weight:500}.pipeline-proof a{font-size:25px}.pipeline-policy{margin-top:28px;font-size:27px!important;color:var(--muted)}
/* === REACH: THE WEEKLY VIEW IS NOW A PUBLIC DEMO === */
.reach-layout{display:grid;grid-template-columns:1160px 490px;gap:80px;margin-top:42px}.reach-layout img{height:600px;object-fit:cover;object-position:top}
.reach-copy{padding-top:20px}.reach-copy h3{font-size:38px;margin:24px 0 11px}.reach-copy p{font-size:28px;color:var(--muted)}
/* === CLOSE: THE OUTCOME, LIVE LINK, AND A REAL SCANNABLE QR === */
.final-close{background:var(--ink);color:var(--paper)}.final-close .eyebrow,.final-close .slide-footer{color:#c0d0be}
.final-close h2{font-size:100px;max-width:1250px;line-height:1.05;margin-top:65px}.closing-workflow{display:flex;gap:32px;font-size:36px;margin-top:50px;align-items:center}
.closing-workflow span+span:before{content:'→';margin-right:32px;color:var(--warm)}
.closing-demo{margin-top:65px;max-width:1230px;border-top:1px solid #79927d;padding-top:27px}
.closing-demo a{font-size:41px;text-underline-offset:9px}.guest-line{font-size:28px!important;margin-top:22px}.future-line{font-size:24px!important;color:#cfdbc9;margin-top:28px}
.qr-box{position:absolute;right:105px;top:345px;width:335px;text-align:center}.qr-box img{background:white;width:335px;height:335px;display:block}.qr-box p{font-size:23px;color:#d4e0cf;margin-top:18px}
.final-close .slide-footer{border-top:1px solid #57745d;padding-top:20px}
/* === CHAT AND IDENTITY: LOCAL IMPLEMENTATION, EXPLICIT READINESS === */
.chat-layout{grid-template-columns:650px 1000px;gap:80px;margin-top:40px}.chat-layout .body-copy{gap:24px}.chat-layout p{font-size:29px}
.chat-evidence img{height:500px;object-fit:contain;background:white}.auth-layout{margin-top:38px}.auth-layout .body-copy{gap:24px}.auth-layout p{font-size:29px}
.auth-evidence img{height:545px;object-fit:contain;background:#fff}
/* === REDUCED MOTION AND PRINT: NO REFLOW OR INCOMPLETE REVEALS === */
@media(prefers-reduced-motion:reduce){.reveal{transition:none!important;transition-delay:0s!important;opacity:1;transform:none}}
@media print{.final h1,.final h2,.final h3{break-after:avoid}.final-close{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''

SLIDES = [
('final-cover', '''<div class="eyebrow reveal" data-edit>Graduate seminar / Final project presentation</div>
<h1 class="reveal" data-edit>Smart<br>Schedule.</h1>
<p class="cover-subtitle reveal" data-edit>From a working calendar<br>to a product you can ask.</p>
<div class="cover-status reveal"><span class="tag live" data-edit><span class="live-dot"></span>Live on Azure</span></div>
<div class="outcome-rail reveal"><span class="mini-label" data-edit>The original question, answered</span><div><strong data-edit>Plan the week.</strong><p data-edit>Classes, jobs and personal time.</p></div><div><strong data-edit>Check an offer.</strong><p data-edit>Conflicts and working windows.</p></div><div><strong data-edit>Share the hours.</strong><p data-edit>Availability without private details.</p></div></div>'''),
('recap', '''<div class="eyebrow reveal" data-edit>A brief recap / Since the previous report</div><h2 class="reveal" data-edit>The next steps<br>became working features.</h2>
<div class="recap-grid reveal"><div class="recap-panel before"><span class="mini-label" data-edit>Previous presentation</span><ul><li data-edit>Private accounts &amp; one-time commitments</li><li data-edit>A visual weekly calendar</li><li data-edit>Recurring engine; availability still planned</li></ul></div><div class="recap-panel now"><span class="mini-label" data-edit>This final milestone</span><ul><li data-edit>Complete recurring editing workflows</li><li data-edit>Calculated availability &amp; shift checking</li><li data-edit>Schedule chat, social signup &amp; deployment</li></ul></div></div>
<p class="note-line reveal" data-edit>Still the guiding rule: empty calendar space ≠ willingness to work.</p>'''),
('recurring', '''<div class="eyebrow reveal" data-edit>01 / Complete scheduling workflows</div><h2 class="reveal" data-edit>Schedules change.<br>History stays.</h2>
<div class="two-column reveal"><div class="body-copy"><div><h3 data-edit>Change future hours</h3><div class="revision"><div><span data-edit>Before 30 November</span><strong data-edit>09:00–13:00</strong></div><div><span data-edit>From 30 November</span><strong data-edit>10:00–14:00</strong></div></div></div><div><h3 data-edit>Change one occurrence</h3><p data-edit>Move or cancel a single shift<br>without rewriting the series.</p></div><p class="callout" data-edit>Review dated conflicts before saving.</p></div><figure class="evidence"><div class="browser-label" data-edit>Recurring commitments / Current deployment</div><img class="recurring-image" data-asset="recurring.png" alt="The live recurring commitments screen with fictional classes and job shifts."><figcaption data-edit>Actual deployed interface · Fictional demo schedule</figcaption></figure></div>'''),
('availability', '''<div class="eyebrow reveal" data-edit>02 / Availability is now implemented</div><h2 class="reveal" data-edit>Working windows − commitments<br>= shareable availability.</h2>
<div class="availability-layout reveal"><div><div class="lane-label" data-edit>Willing to work <span>Monday / 08:00–20:00</span></div><div class="willing-lane"></div><div class="demo-axis"><span>08:00</span><span>10:00</span><span>12:00</span><span>14:00</span><span>16:00</span><span>18:00</span><span>20:00</span></div><div class="lane-label" data-edit>Subtract commitments</div><div class="occupied-lane"><div class="class" data-edit>Class<br><small>10:00–12:00</small></div><div class="study" data-edit>Study<br><small>12:00–14:00</small></div></div><div class="lane-label" data-edit>Calculated result</div><div class="free-lane"><div class="first" data-edit>08:00–10:00</div><div class="second" data-edit>14:00–20:00</div></div></div><div><div class="share-answer"><span class="mini-label" data-edit>What the employer receives</span><strong data-edit>Monday<br>08:00–10:00<br>14:00–20:00</strong><p data-edit>Dates and hours only.<br>No commitment details.</p></div><figure class="availability-proof"><img data-asset="monday-availability.png" alt="The live availability screen confirms Monday free hours of 08:00–10:00 and 14:00–20:00."><figcaption data-edit>The same result in the deployed app.</figcaption></figure></div></div>
<p class="note-line" data-edit>Weekly patterns + date overrides · One-time and recurring commitments included</p>'''),
('shift', '''<div class="eyebrow reveal" data-edit>03 / Check an offer without saving it</div><h2 class="reveal" data-edit>Can I accept<br>this particular shift?</h2>
<div class="two-column shift-layout reveal"><div><div class="decision"><strong data-edit><span class="dot"></span>Available</strong><p data-edit>The whole offer fits the working window<br>and overlaps no commitments.</p></div><div class="decision"><strong data-edit><span class="dot"></span>Commitment conflict</strong><p data-edit>Monday 11:00–11:30 overlaps the class.</p></div><div class="decision"><strong data-edit><span class="dot"></span>Outside working hours</strong><p data-edit>Reported separately from conflicts.</p></div></div><figure class="evidence shift-evidence"><img data-asset="shift-result.png" alt="Actual shift-check result: Monday 11:00–11:30 is unavailable because it overlaps the weekly class."><figcaption data-edit>Actual result · The saved schedule is unchanged</figcaption></figure></div>'''),
('chat', '''<div class="eyebrow reveal" data-edit>04 / Quick answers without switching pages</div><h2 class="reveal" data-edit>Ask your schedule.<br>Get a grounded answer.</h2>
<div class="two-column chat-layout reveal"><div class="body-copy"><div><h3 data-edit>“When can I work next week?”</h3><p data-edit>Chat panel + full chat page.<br>Follow-up context; fresh schedule lookups.</p></div><div><h3 data-edit>Python owns the calendar</h3><p data-edit>Dates, weekdays and availability totals<br>come from scheduling services.</p></div><div><h3 data-edit>Read-only, free-tier demo</h3><p data-edit>Groq interprets broader questions.<br>Simple reports need no model request.</p></div></div><figure class="evidence chat-evidence"><img data-asset="chat.png" alt="Actual local chat interface with an availability answer calculated from the fictional demo schedule."><figcaption data-edit>Local app capture · Real service-calculated report · No model-generated hours</figcaption></figure></div>
<p class="note-line" data-edit>Free-tier inference needs internet and quota · No schedule writes or Calendar access</p>'''),
('reliability', '''<div class="eyebrow reveal" data-edit>05 / Evidence behind the workflow</div><h2 class="reveal" data-edit>Reliable behavior.<br>Across difficult cases.</h2>
<div class="reliability-layout reveal"><div><div class="test-number" data-edit>596</div><p class="test-number-label" data-edit>tests passed in the<br>latest local PostgreSQL run</p><p class="previous-count" data-edit>Previous report: 189 tests recorded.</p></div><div><div class="verified-grid"><div><h3 data-edit>Private accounts</h3><p data-edit>Ownership, OAuth signup and sessions.</p></div><div><h3 data-edit>Changing schedules</h3><p data-edit>Recurring revisions and exceptions.</p></div><div><h3 data-edit>Time boundaries</h3><p data-edit>Overnight shifts and clock changes.</p></div><div><h3 data-edit>Grounded answers</h3><p data-edit>Dates and availability reports from Python.</p></div></div><div class="rehearsal-strip" data-edit>Plus a Docker rehearsal:<br>HTTPS · Login · Persistence · Backup restore</div></div></div>
<p class="note-line" data-edit>25 November local run: 596 passed · 4 skipped · 2 Docker/WSL environment failures</p>'''),
('cloud', '''<div class="eyebrow reveal" data-edit>06 / From local development to Azure</div><h2 class="reveal" data-edit>A working cloud deployment.</h2><p class="url-ribbon reveal"><a href="https://schedule.khadkabijay.com.np/" target="_blank" rel="noopener" data-edit>schedule.khadkabijay.com.np</a></p>
<div class="cloud-outline reveal"><div class="cloud-label" data-edit>One Azure Ubuntu VM / Docker Compose</div><div class="cloud-nodes"><div class="cloud-node"><span class="mini-label" data-edit>Public entry</span><h3 data-edit>Caddy</h3><p data-edit>HTTPS certificates<br>and reverse proxy</p></div><div class="cloud-arrow" aria-hidden="true">→</div><div class="cloud-node primary"><span class="mini-label" data-edit>Application</span><h3 data-edit>Django + Gunicorn</h3><p data-edit>Private scheduling<br>and service-layer rules</p></div><div class="cloud-arrow" aria-hidden="true">→</div><div class="cloud-node"><span class="mini-label" data-edit>Private storage</span><h3 data-edit>PostgreSQL 17</h3><p data-edit>Persistent schedules<br>and database backups</p></div></div></div>
<div class="cloud-notes reveal"><p data-edit>Separate development<br>and production settings.</p><p data-edit>One packaged image.<br>Credentials stay on the VM.</p><p data-edit>A practical demo setup.<br>One server, no automatic failover.</p></div>'''),
('cicd', '''<div class="eyebrow reveal" data-edit>07 / Continuous integration and deployment</div><h2 class="reveal" data-edit>Push code.<br>Prove it. Deploy it.</h2>
<div class="pipeline reveal"><div class="pipeline-node"><span class="step" data-edit>01 / GitHub</span><h3 data-edit>Push to main</h3><p data-edit>Exact Git commit</p></div><span class="pipeline-arrow" aria-hidden="true">→</span><div class="pipeline-node"><span class="step" data-edit>02 / Validate</span><h3 data-edit>Test &amp; build</h3><p data-edit>PostgreSQL tests<br>+ Docker rehearsal</p></div><span class="pipeline-arrow" aria-hidden="true">→</span><div class="pipeline-node"><span class="step" data-edit>03 / Release</span><h3 data-edit>Back up &amp; migrate</h3><p data-edit>The exact tested image.<br>Existing data retained.</p></div><span class="pipeline-arrow" aria-hidden="true">→</span><div class="pipeline-node last"><span class="step" data-edit>04 / Azure</span><h3 data-edit>Deploy &amp; verify</h3><p data-edit>Healthy app +<br>public HTTPS checks</p></div></div>
<div class="pipeline-proof reveal"><strong data-edit>✓ First complete automated deployment passed</strong><a href="https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/runs/45514354911" target="_blank" rel="noopener" data-edit>View the verified GitHub Actions run ↗</a></div><p class="pipeline-policy reveal" data-edit>Pull requests test only · Main deploys · OIDC sign-in · Temporary SSH access removed</p>'''),
('reach', '''<div class="eyebrow reveal" data-edit>08 / Easier access for demo participants</div><h2 class="reveal" data-edit>Sign in.<br>Start your own schedule.</h2>
<div class="two-column auth-layout reveal"><div class="body-copy"><div><h3 data-edit>Google or GitHub</h3><p data-edit>First sign-in creates a private account.<br>Returning users keep their schedule.</p></div><div><h3 data-edit>Existing login still works</h3><p data-edit>Username and password remain available.<br>Shared fictional guest for the demo.</p></div><div><h3 data-edit>Setup before public use</h3><p data-edit>Register provider apps, configure credentials,<br>then deploy and rehearse both sign-ins.</p></div></div><figure class="evidence auth-evidence"><img data-asset="social-login.png" alt="Local login-page preview showing Google and GitHub sign-in buttons alongside username and password."><figcaption data-edit>Local configured-provider preview · Live OAuth setup pending</figcaption></figure></div>'''),
('final-close', '''<div class="eyebrow reveal" data-edit>Delivered outcome / Thank you</div><h2 class="reveal" data-edit>“When can I<br>actually work?”</h2><div class="closing-workflow reveal"><span data-edit>Plan a week</span><span data-edit>Check an offer</span><span data-edit>Share the hours</span></div>
<div class="closing-demo reveal"><a href="https://schedule.khadkabijay.com.np/" target="_blank" rel="noopener" data-edit>schedule.khadkabijay.com.np</a><p class="guest-line" data-edit>Guest: schedule_demo &nbsp; / &nbsp; DemoSchedule!2026</p><p class="future-line" data-edit>Available locally: read-only chat and social signup.<br>Next: Calendar integration, voice and confirmed schedule changes.</p></div><div class="qr-box reveal"><a href="https://schedule.khadkabijay.com.np/" target="_blank" rel="noopener"><img data-asset="demo-qr.svg" alt="QR code opening https://schedule.khadkabijay.com.np/"></a><p data-edit>Scan for the hosted scheduling demo</p></div>'''),
]


def main():
    old = (PREVIOUS / 'index.html').read_text()
    css = old[old.index('<style>') + 7:old.index('</style>')]
    required = (Path('/home/bijay/.codex/skills/frontend-slides/viewport-base.css')).read_text().strip()
    assert required in css, 'Keep the complete fixed-stage base from the existing deck'
    script = old[old.index('<script>') + 8:old.rindex('</script>')]
    script = script.replace('smart-schedule-seminar-v1', 'smart-schedule-final-v2').replace('Target finish: 2:55', 'Target finish: 5:50')
    script = script.replace('n>=180', 'n>=360').replace('smart-schedule-seminar.html', 'smart-schedule-final.html')
    notes_document = (ROOT / 'speaker-notes.md').read_text()
    notes = re.findall(r'^## \d+\..*?\n\n(.*?)(?=\n## |\Z)', notes_document, re.M | re.S)
    assert len(notes) == len(SLIDES) == len(TIMES) == 11 and sum(TIMES) == 350
    parts = []
    for index, ((kind, markup), note) in enumerate(zip(SLIDES, notes)):
        markup = re.sub(r'data-asset="([^"]+)"', lambda m: 'src="data:' + (mimetypes.guess_type(m[1])[0] or 'image/png') + ';base64,' + base64.b64encode((ROOT / 'assets' / m[1]).read_bytes()).decode() + '"', markup)
        active = ' active visible' if index == 0 else ''
        parts.append(f'<section class="slide final {kind}{active}" aria-label="{index+1}. {escape(LABELS[index])}" aria-hidden="{str(index != 0).lower()}" data-seconds="{TIMES[index]}">\n' + markup + f'\n<footer class="slide-footer"><span>Smart Schedule <span class="footer-dot">/</span> Final seminar</span><span>{index+1:02} / 11</span></footer>\n<aside class="speaker-notes" hidden>{escape(" ".join(note.split()))}</aside>\n</section>')
    controls = old[old.index('<nav class="deck-controls"'):old.index('<script>')].replace('1 / 6', '1 / 11')
    html = '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="A six-minute final seminar: Smart Schedule recap, implemented workflows, grounded schedule chat, social signup, Azure deployment and CI/CD."><title>Smart Schedule — Final Seminar</title><style>\n' + css + STYLES + '\n</style></head><body>\n<!-- Eleven speaker-led slides, 350 seconds plus a 10-second buffer. -->\n<div class="deck-viewport"><main class="deck-stage" id="deckStage">' + '\n'.join(parts) + '</main></div>\n' + controls + '<script>' + script + '</script></body></html>\n'
    (ROOT / 'index.html').write_text(html)
    shutil.copyfile(PREVIOUS / 'FONT-LICENSE.txt', ROOT / 'FONT-LICENSE.txt')
    print(f'Built 11 standalone slides. Spoken script: {sum(len(note.split()) for note in notes)} words. Target: 350 seconds.')


if __name__ == '__main__':
    main()
