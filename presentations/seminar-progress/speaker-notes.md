# Smart Schedule — three-minute seminar script

Six slides, 175 seconds of planned speaking time, and a 5-second buffer. Rehearse at a comfortable pace; actual delivery time depends on pauses. This is a progress report, so no live login or app setup is needed.

## 1. A real scheduling problem · 0:00–0:20

My project is Smart Schedule and Availability Manager. It comes from a problem I face as a student balancing classes and work, and that my wife faces working two jobs. When an employer asks when we can work, answering means checking several commitments manually.

## 2. The project idea · 0:20–0:45

The idea is one private place for classes, shifts, and personal commitments. Users can see their week, spot overlapping commitments, and eventually generate availability to share with an employer. The key distinction is that an empty calendar slot does not automatically mean I am willing to work. Study time and personal time also need protection.

## 3. How availability will work · 0:45–1:20

Here is a simple example of the planned calculation. Suppose I am willing to work on Monday from eight in the morning until eight in the evening. A class takes ten until twelve, and protected study time takes twelve until two. The remaining work availability is eight until ten, and two until eight. The employer would receive only those available intervals, without seeing my private commitment details. This calculation is the next major feature.

## 4. Progress so far · 1:20–2:05

So far, I have built private login, commitment sources, and screens to create, edit, and delete one-time commitments, including overnight shifts. The weekly calendar shown here is working, with source colors, navigation, details, overlap indicators, and a phone agenda. One-time saves also warn about conflicts. The recurring backend supports weekly schedules, future changes, and one-off exceptions, although recurring editing forms still need to be added. The latest recorded verification reports 189 PostgreSQL tests passing.

## 5. The technical approach · 2:05–2:35

The application uses Python, Django, and PostgreSQL, with Django templates and Bootstrap for the interface. Scheduling rules live in service modules, separate from the views, so future API endpoints can reuse them. One technical challenge is handling overnight commitments and daylight-saving changes while preserving earlier schedules when recurring hours change. These cases are covered in the existing test suite.

## 6. What comes next · 2:35–2:55

Next, I will connect recurring entry and conflict checks, then implement working windows, availability calculation, and copyable employer text. After that, I plan to explore natural-language entry and Google Calendar integration. The goal is a practical answer to one question: when can I actually work?

## Rehearsal reminders

- Script: approximately 356 words. The time allocations include pauses.
- Start the timer with **T** on slide 1. Aim to finish by 2:55.
- If behind, shorten slide 5 to: “Django handles the interface, PostgreSQL stores schedules, and service modules keep the scheduling rules reusable.”
- The availability example is planned behavior, not a working feature.
- Recurring backend services exist; recurring entry forms and combined save-conflict checks remain upcoming.
- The 189-test number is the latest recorded application verification in the project docs, not a fresh test run for this deck.
- Speaker notes (N) appear on the current screen. Close them before projecting; use this script on a second device if needed.
- After editing slide text, check that it still fits. The accompanying script and PDF need updating separately.
