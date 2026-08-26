"""
knowledge_base.py — Built-in mental health knowledge base for MindWell RAG.

Contains curated, evidence-based content across 8 categories:
  1. CBT Techniques
  2. Breathing & Relaxation Exercises
  3. Sleep Hygiene
  4. Grounding Techniques
  5. Coping Strategies
  6. Anxiety & Panic Management
  7. Depression & Low Mood
  8. Crisis & Safety Resources

Run once to seed the rag_documents table:
    python knowledge_base.py

All chunks are stored with user_id = NULL (global) — available to every user.
"""

KNOWLEDGE_BASE = [

    # ================================================================
    # 1. CBT TECHNIQUES
    # ================================================================
    {
        "source": "CBT Techniques",
        "content": """
Cognitive Behavioral Therapy (CBT) is one of the most evidence-based approaches
for treating anxiety, depression, stress, and many other mental health challenges.
CBT works on the principle that our thoughts, feelings, and behaviors are all
connected. Negative or distorted thoughts lead to negative feelings, which lead
to unhelpful behaviors — and the cycle repeats. By identifying and challenging
distorted thoughts, we can change how we feel and how we act.

CBT is practical and skill-based. It teaches you tools you can use for the rest
of your life. It typically involves: identifying automatic negative thoughts,
examining evidence for and against those thoughts, replacing distorted thinking
with more balanced thinking, and gradually changing avoidance behaviors.
        """.strip()
    },
    {
        "source": "CBT Techniques",
        "content": """
Thought Records (also called Thought Diaries) are a core CBT tool.
When you notice a strong negative emotion, use this 5-step process:

Step 1 — Situation: What happened? Where were you? Who was involved?
Step 2 — Emotions: What did you feel? Rate intensity 0-100%.
Step 3 — Automatic Thought: What went through your mind? What did you believe?
Step 4 — Evidence: What evidence supports this thought? What evidence goes against it?
Step 5 — Balanced Thought: Write a more realistic, balanced version of the thought.
         Re-rate your emotion intensity after the balanced thought.

Example:
Situation: Friend didn't reply to my message for 2 days.
Emotion: Anxiety (80%), Sadness (70%)
Automatic Thought: "They hate me. I've done something wrong."
Evidence FOR: They haven't replied. Evidence AGAINST: They're often busy, replied quickly before.
Balanced Thought: "They're probably busy. One unanswered message doesn't mean they hate me."
New emotion: Anxiety (30%), Sadness (20%)
        """.strip()
    },
    {
        "source": "CBT Techniques",
        "content": """
Common Cognitive Distortions (Thinking Errors) in CBT:

1. All-or-Nothing Thinking: Seeing things in black and white with no middle ground.
   "If I'm not perfect, I'm a total failure."

2. Catastrophizing: Expecting the worst possible outcome.
   "I made a mistake at work — I'll definitely get fired."

3. Mind Reading: Assuming you know what others are thinking.
   "They didn't smile at me — they must dislike me."

4. Overgeneralization: Drawing broad conclusions from one event.
   "This went wrong, so everything always goes wrong for me."

5. Emotional Reasoning: Believing something is true because it feels true.
   "I feel stupid, therefore I am stupid."

6. Should Statements: Rigid rules about how you or others must behave.
   "I should always be productive. I shouldn't need help."

7. Personalization: Blaming yourself for things outside your control.
   "My friend is upset — it must be something I did."

8. Filtering: Focusing only on the negatives while ignoring positives.
   "The presentation went well but I stumbled once — it was a disaster."

Recognizing which distortion is active is the first step to challenging it.
        """.strip()
    },
    {
        "source": "CBT Techniques",
        "content": """
If thoughts like "I keep thinking I'm a failure," "I feel like such a
failure," "why do I always think the worst about myself," or "I can't stop
these negative thoughts" sound familiar, you're describing what CBT calls a
cognitive distortion — a thinking pattern that feels true but distorts
reality. Naming the pattern (see Common Cognitive Distortions) is the first
step; a thought record is the tool for actually challenging it.
        """.strip()
    },
    {
        "source": "CBT Techniques",
        "content": """
Behavioral Activation is a CBT technique for depression and low mood.
Depression causes withdrawal from activities, which worsens mood further —
creating a cycle. Behavioral Activation breaks this cycle by scheduling
meaningful, enjoyable, or achievable activities even when motivation is low.

Key principle: Action comes before motivation, not after.
You don't wait to feel like doing something — you do it, and the feeling follows.

Steps:
1. Track your current activities and mood for 3-5 days to see the connection.
2. Identify activities that previously gave you pleasure or a sense of achievement.
3. Schedule 1-2 small activities each day (start very small — a 5-minute walk counts).
4. Rate your mood before and after each activity.
5. Gradually increase activity as mood improves.

Categories of helpful activities:
- Achievement: tasks that give a sense of accomplishment (tidying one drawer)
- Pleasure: activities you enjoy (music, cooking, reading)
- Social: connecting with others (even a brief text to a friend)
- Physical: any movement (stretching, a short walk)
        """.strip()
    },
    {
        "source": "CBT Techniques",
        "content": """
The ABC Model of CBT (Albert Ellis):

A — Activating Event: The situation or trigger that occurred.
B — Belief: What you told yourself about the event (the thought).
C — Consequence: The emotional and behavioral result of the belief.

Most people think A causes C directly. CBT shows that B (your belief) is the
real driver of C. Two people can experience the same A and have completely
different C depending on their B.

Example:
A: You receive critical feedback on your work.
B1: "I'm terrible at this. I'll never be good enough." → C1: Shame, giving up.
B2: "This is hard to hear, but it's useful information for improvement." → C2: Motivation.

Disputing (D): Challenge the belief — is it logical? Is it based on evidence?
   Is it helping or hurting you? What would you tell a friend in this situation?
New Effect (E): The new emotion and behavior after a more balanced belief.
        """.strip()
    },

    # ================================================================
    # 2. BREATHING & RELAXATION
    # ================================================================
    {
        "source": "Breathing Exercises",
        "content": """
Box Breathing (4-4-4-4 technique) — Used by Navy SEALs and athletes to calm
the nervous system rapidly. Activates the parasympathetic nervous system,
reducing cortisol and adrenaline within minutes.

How to do it:
1. Inhale slowly through your nose for 4 counts.
2. Hold your breath for 4 counts.
3. Exhale slowly through your mouth for 4 counts.
4. Hold empty for 4 counts.
5. Repeat 4-6 times.

When to use it: Before a stressful event, during anxiety, after a panic attack,
before sleep, or any time you feel overwhelmed.

The science: Slow, controlled breathing directly stimulates the vagus nerve,
triggering the relaxation response and reducing heart rate and blood pressure.
        """.strip()
    },
    {
        "source": "Breathing Exercises",
        "content": """
4-7-8 Breathing — Developed by Dr. Andrew Weil. Particularly effective for
falling asleep and calming acute anxiety.

How to do it:
1. Exhale completely through your mouth.
2. Close your mouth and inhale through your nose for 4 counts.
3. Hold your breath for 7 counts.
4. Exhale completely through your mouth for 8 counts (make a whoosh sound).
5. This is one cycle. Repeat 3-4 times.

Important: The ratio 4:7:8 matters more than the speed. Start slowly.
The extended exhale is key — it activates the body's natural relaxation response.

Best used for: Difficulty sleeping, acute anxiety, anger management,
stress after a difficult conversation.
        """.strip()
    },
    {
        "source": "Breathing Exercises",
        "content": """
Diaphragmatic Breathing (Belly Breathing) — The foundation of all relaxation
breathing. Most people breathe shallowly into the chest when stressed.
Belly breathing corrects this and signals safety to the nervous system.

How to do it:
1. Sit or lie down comfortably.
2. Place one hand on your chest, one on your belly.
3. Breathe in through your nose — the belly hand should rise, chest hand stays still.
4. Exhale slowly through your mouth — belly falls.
5. Breathe at a natural pace, just deeper than usual.
6. Practice for 5-10 minutes.

Why it works: The diaphragm is directly connected to the vagus nerve.
Engaging it with each breath sends "calm down" signals to the brain.

Practice this daily (not just in crisis) to retrain your default breathing pattern.
        """.strip()
    },
    {
        "source": "Breathing Exercises",
        "content": """
Progressive Muscle Relaxation (PMR) — A technique to release physical tension
stored in the body due to stress and anxiety.

How to do it:
1. Find a comfortable position (lying down is ideal).
2. Starting from your feet, tense each muscle group tightly for 5-7 seconds.
3. Then release the tension completely for 20-30 seconds. Notice the difference.
4. Move up the body: feet → calves → thighs → abdomen → hands → arms →
   shoulders → face.
5. Total time: about 15-20 minutes.

The key is the contrast between tension and release. This helps your brain
learn what deep relaxation actually feels like in the body.

Best for: Chronic tension headaches, trouble sleeping, generalized anxiety,
physical symptoms of stress (tight shoulders, clenched jaw, stomach knots).
        """.strip()
    },

    # ================================================================
    # 3. SLEEP HYGIENE
    # ================================================================
    {
        "source": "Sleep Hygiene",
        "content": """
Sleep Hygiene refers to habits and practices that support consistent, quality sleep.
Poor sleep significantly worsens anxiety, depression, focus, and emotional regulation.

Core sleep hygiene principles:

1. Consistent sleep schedule: Go to bed and wake up at the same time every day —
   including weekends. This anchors your circadian rhythm.

2. The 20-minute rule: If you can't sleep after 20 minutes, get up and do something
   calm (reading, gentle stretching) until you feel sleepy. Don't lie in bed awake —
   it trains your brain to associate bed with wakefulness.

3. Wind-down routine: Spend 30-60 minutes before bed doing calming activities.
   Your brain needs a transition signal from day mode to sleep mode.

4. Temperature: Keep your bedroom cool (16-19°C / 60-67°F). Core body temperature
   needs to drop to initiate sleep.

5. Darkness: Blackout curtains or a sleep mask. Even small amounts of light suppress
   melatonin production.

6. Noise: Use white noise, earplugs, or a fan if your environment is noisy.
        """.strip()
    },
    {
        "source": "Sleep Hygiene",
        "content": """
What to avoid for better sleep:

Screens (phones, TV, laptops): Blue light suppresses melatonin for up to 3 hours.
Use night mode or stop screens 1 hour before bed. The stimulation of social media
and news also raises alertness, making it harder to sleep.

Caffeine: Has a half-life of 5-7 hours. A coffee at 3pm still has half its caffeine
in your system at 10pm. Cut off caffeine by 2pm if you struggle with sleep.

Alcohol: While it helps you fall asleep initially, it fragments sleep in the second
half of the night and suppresses REM sleep (the emotionally restorative phase).

Heavy meals: Eating a large meal within 2-3 hours of bedtime can cause discomfort
and interfere with sleep onset.

Naps after 3pm: Late afternoon naps reduce sleep pressure at night, making it
harder to fall asleep at your regular time.

Watching the clock: Checking the time when you can't sleep increases anxiety.
Turn the clock away or remove it from sight.
        """.strip()
    },
    {
        "source": "Sleep Hygiene",
        "content": """
Cognitive approaches to insomnia (CBT-I):

Sleep anxiety (worrying about not sleeping) is often the biggest barrier to sleep.
The worry about not sleeping makes the brain more alert — the opposite of what's needed.

Stimulus control: Only use your bed for sleep and sex. Don't work, watch TV,
or use your phone in bed. This rebuilds the mental association between bed and sleep.

Sleep restriction therapy: Temporarily restrict the time you spend in bed to match
your actual sleep time. This builds up "sleep pressure" and consolidates fragmented sleep.
Gradually extend the window as sleep efficiency improves.

Paradoxical intention: Instead of trying to fall asleep, try to stay awake (while lying
still with eyes closed). This removes the performance anxiety around sleep.

Cognitive restructuring for sleep: Challenge thoughts like "I must get 8 hours or
tomorrow will be ruined." Most people function adequately on less sleep than they think.
The catastrophizing about bad sleep often causes more impairment than the sleep loss itself.
        """.strip()
    },

    # ================================================================
    # 4. GROUNDING TECHNIQUES
    # ================================================================
    {
        "source": "Grounding Techniques",
        "content": """
Grounding techniques bring your attention back to the present moment and interrupt
anxiety, panic, dissociation, or overwhelming emotion. They work by engaging your
senses to anchor you in the here-and-now rather than spiraling in your thoughts.

The 5-4-3-2-1 Technique (most widely used grounding method):

Name 5 things you can SEE right now.
Name 4 things you can physically FEEL (your feet on the floor, the chair beneath you).
Name 3 things you can HEAR right now.
Name 2 things you can SMELL (or two things you like the smell of).
Name 1 thing you can TASTE.

Do this slowly, paying genuine attention to each sensation. By the time you reach 1,
your nervous system has usually shifted out of the fight-or-flight response.

Best for: Panic attacks, dissociation, flashbacks, overwhelming anxiety, feeling
"not real" or disconnected from your body.
        """.strip()
    },
    {
        "source": "Grounding Techniques",
        "content": """
Physical grounding techniques — when anxiety or panic is very intense:

Cold water: Hold ice cubes, run cold water over your wrists, or splash cold water
on your face. Cold activates the dive reflex, rapidly slowing heart rate.

Feet on floor: Press both feet firmly into the floor. Notice the pressure and
temperature. Say to yourself: "I am here. I am safe. My feet are on the ground."

The 3-3-3 Rule: Name 3 things you see, 3 sounds you hear, move 3 parts of your body.
Quick and portable — works in any situation.

Butterfly Hug (for trauma/distress): Cross arms over chest, hands on shoulders.
Alternately tap left and right shoulder slowly. This bilateral stimulation calms
the amygdala (the brain's alarm system).

Safe place visualization: Close your eyes, picture a place where you feel completely
safe and calm (real or imagined). Engage all five senses in the visualization —
what do you see, hear, smell, feel, taste there?
        """.strip()
    },

    # ================================================================
    # 5. COPING STRATEGIES
    # ================================================================
    {
        "source": "Coping Strategies",
        "content": """
Healthy vs. Unhealthy Coping Strategies:

Unhealthy coping strategies provide short-term relief but worsen problems long-term:
- Alcohol and substance use
- Avoidance and withdrawal
- Excessive sleeping
- Emotional eating / restricting food
- Self-harm
- Rumination (going over and over the problem without resolution)
- Venting without problem-solving
- Scrolling social media for hours

Healthy coping strategies address the emotion and support recovery:
- Physical exercise (even a 10-minute walk significantly reduces cortisol)
- Talking to a trusted person
- Journaling thoughts and feelings
- Creative expression (drawing, music, writing)
- Mindfulness and meditation
- Problem-solving (when the stressor is solvable)
- Distraction (useful short-term — a walk, a film, a book)
- Self-compassion practices
- Professional support (therapy, counseling)
        """.strip()
    },
    {
        "source": "Coping Strategies",
        "content": """
If you're thinking "I keep using bad habits to deal with my problems, what
should I do instead," or "my coping mechanisms aren't working anymore," or
"I don't know what else to do besides [drinking / avoiding / scrolling],"
that's a sign it's worth swapping an unhealthy coping strategy for a
healthy one (see Healthy vs. Unhealthy Coping Strategies) rather than a
sign anything is wrong with you for coping the way you have been.
        """.strip()
    },
    {
        "source": "Coping Strategies",
        "content": """
The TIPP Skills (DBT technique for intense emotions):

When emotions feel out of control, TIPP helps regulate quickly:

T — Temperature: Use cold water on the face or hold ice. This activates the
    mammalian dive reflex, lowering heart rate in seconds.

I — Intense Exercise: Do 20 minutes of vigorous exercise to burn off adrenaline.
    Running, jumping jacks, push-ups — anything that raises your heart rate.

P — Paced Breathing: Slow your breathing to 5-6 breaths per minute (breathe in
    for 5 counts, out for 5 counts). This directly activates the parasympathetic system.

P — Progressive Muscle Relaxation: Systematically tense and release muscle groups
    from feet to face to release physical tension.

TIPP works on the body first because when emotional arousal is very high,
cognitive techniques (like thought records) are hard to apply. Bring the arousal
down with TIPP first, then use cognitive strategies.
        """.strip()
    },
    {
        "source": "Coping Strategies",
        "content": """
Journaling for mental health — evidence-based approaches:

Expressive writing: Write freely about your deepest thoughts and feelings about
a stressful event for 15-20 minutes. Don't worry about grammar or structure.
Research by James Pennebaker shows this reduces anxiety, improves immune function,
and helps process trauma over 3-4 sessions.

Gratitude journaling: Write 3 specific things you're grateful for each day.
Specificity matters — not "my family" but "my sister texted to check on me today."
This gradually retrains attention away from threat-focused thinking.

Worry journaling: Dedicate a specific 15-minute "worry time" to write all your
worries. Outside this time, postpone worries to the next session. This contains
worry rather than letting it spread through the day.

Values journaling: Write about what matters most to you and whether your actions
align with those values. Helps with direction and meaning when life feels empty.
        """.strip()
    },

    # ================================================================
    # 6. ANXIETY & PANIC MANAGEMENT
    # ================================================================
    {
        "source": "Anxiety and Panic Management",
        "content": """
Understanding Panic Attacks:

A panic attack is a sudden surge of intense fear accompanied by physical symptoms:
racing heart, shortness of breath, chest tightness, dizziness, tingling,
sweating, feeling of unreality, or fear of dying or losing control.

Panic attacks are NOT dangerous. They cannot cause a heart attack, cause you to
stop breathing, or cause you to lose your mind. They are the body's alarm system
misfiring — giving a "danger" response when no real danger exists.

The peak of a panic attack typically lasts 10-15 minutes, then subsides on its own.

What makes panic worse: Catastrophizing the sensations ("I'm dying"), trying to
escape the situation, deep fast breathing (hyperventilating), tensing the body.

What helps: Accepting the sensations without fighting them ("this is uncomfortable
but not dangerous"), slow diaphragmatic breathing, staying in the situation,
reminding yourself "this will pass, it always does."
        """.strip()
    },
    {
        "source": "Anxiety and Panic Management",
        "content": """
Exposure Therapy (Facing Fears) — The gold standard for anxiety:

Avoidance maintains and strengthens anxiety. Every time we avoid a feared situation,
we tell our brain "that was so dangerous I had to escape" — making the fear bigger.
Gradual exposure reverses this.

Steps:
1. Create a fear ladder: List feared situations from least scary (1) to most scary (10).
2. Start with level 2-3 situations — challenging but manageable.
3. Stay in the situation until anxiety naturally drops by at least 50% (usually 20-45 min).
4. Repeat until the situation no longer triggers significant anxiety.
5. Move up the ladder gradually.

Key principle: You must stay long enough for anxiety to reduce ON ITS OWN (not by
escaping). This teaches your brain that the feared situation is actually safe.

Imaginal exposure: For situations that can't be physically practiced, vividly
imagining the feared scenario in detail can also reduce anxiety over time.
        """.strip()
    },
    {
        "source": "Anxiety and Panic Management",
        "content": """
Worry management techniques:

The Worry Tree (CBT tool):
Ask: "Is this worry about something real and current, or a hypothetical 'what if'?"

If REAL and current → Problem-solve: What can I do about this right now?
   → Do it, plan it, or accept you can't control it.

If HYPOTHETICAL → Let it go: Hypothetical worries cannot be solved.
   Use mindfulness to acknowledge the thought without engaging with it.
   "I notice I'm having the thought that X might happen."

Scheduled worry time: Set aside 15-20 minutes daily as your "worry time."
When a worry arises outside this time, write it down and postpone it.
Most worries feel less urgent when you return to them during the scheduled time.

The 5-year test: "Will this matter in 5 years?" Most daily worries won't.
This provides perspective without dismissing the current feeling.
        """.strip()
    },

    # ================================================================
    # 7. DEPRESSION & LOW MOOD
    # ================================================================
    {
        "source": "Depression and Low Mood",
        "content": """
Understanding Depression:

People experiencing depression often describe it in their own words rather
than clinical terms: "I feel hopeless and empty," "nothing brings me joy
anymore," "I don't see the point in anything," "I just feel numb all the
time," or "I'm so tired of feeling this way." If any of that sounds like
you, what you're describing has a name, and it responds to support.

Depression is more than feeling sad. It is a persistent state that affects:
- Mood (persistent sadness, emptiness, irritability)
- Energy (fatigue, feeling slowed down)
- Thinking (difficulty concentrating, negative thoughts, hopelessness)
- Behavior (withdrawal, loss of interest in previously enjoyed activities)
- Physical (sleep changes, appetite changes, physical aches)
- Self-view (worthlessness, guilt, self-criticism)

Depression lies to you. It tells you that nothing will help, that you've always
been this way, that people don't care, that the future is hopeless. These are
symptoms of the illness — not facts about reality.

Recovery is possible. Most people with depression recover with appropriate support,
whether that is therapy, medication, lifestyle changes, or a combination.
Reaching out for help is a sign of strength, not weakness.
        """.strip()
    },
    {
        "source": "Depression and Low Mood",
        "content": """
"I just feel numb all the time and don't care about anything anymore" is
one of the most common ways people describe depression - not sadness
exactly, but a flatness where things that used to matter stop registering.
Emotional numbness and loss of interest (anhedonia) are core depression
symptoms, not a sign that you've stopped caring as a person. It's one of
the most treatable parts of depression to respond to support.
        """.strip()
    },
    {
        "source": "Depression and Low Mood",
        "content": """
Self-compassion practices for low mood and self-criticism:

Self-compassion (Dr. Kristin Neff) has three components:

1. Self-kindness: Treating yourself with the same care and understanding you
   would offer a good friend. Notice self-critical thoughts and ask:
   "Would I say this to someone I love?"

2. Common humanity: Recognizing that suffering and imperfection are part of
   the shared human experience — not a sign that something is uniquely wrong with you.
   "Many people feel this way. I am not alone in this."

3. Mindful awareness: Holding your pain in balanced awareness without suppressing
   it or over-identifying with it. "I notice I am feeling sad right now."

Self-compassion break (1-2 minutes):
"This is a moment of suffering. [Mindfulness]
Suffering is part of life. I am not alone. [Common humanity]
May I be kind to myself right now. [Self-kindness]
May I give myself the compassion I need."
        """.strip()
    },
    {
        "source": "Depression and Low Mood",
        "content": """
Rumination vs. Reflection — a key distinction in depression:

Rumination: Repetitive, passive focus on distress without moving toward solutions.
"Why am I like this? Why does this always happen to me? What's wrong with me?"
Rumination maintains and deepens depression. It feels like problem-solving but isn't.

Reflection: Active, purposeful thinking aimed at understanding and moving forward.
"What do I need right now? What is one small step I can take?"

How to interrupt rumination:
1. Notice you're ruminating (this takes practice).
2. Absorbing activity: Do something that requires focused attention
   (puzzles, cooking, playing an instrument) — rumination needs a free mind.
3. Physical movement: Walking, especially in nature, reduces rumination significantly.
4. Schedule it: "I'll think about this at 5pm for 15 minutes, not now."
5. Ask "what?" not "why?": "What am I feeling?" is more helpful than "Why do I feel this?"
        """.strip()
    },

    # ================================================================
    # 8. CRISIS & SAFETY RESOURCES
    # ================================================================
    {
        "source": "Crisis Resources",
        "content": """
If you are having thoughts of suicide or self-harm, please reach out immediately.
You do not have to face this alone. Help is available.

You might be thinking things like "I don't want to live anymore," "I am
thinking about ending my life," "I can't do this anymore," "I want it all
to stop," or "everyone would be better off without me." If any of that is
what you're feeling right now, please keep reading and reach out immediately.

International crisis helplines:
- International Association for Suicide Prevention: https://www.iasp.info/resources/Crisis_Centres/
- Crisis Text Line (US): Text HOME to 741741
- Samaritans (UK/Ireland): 116 123 (free, 24/7)
- Lifeline (Australia): 13 11 14
- iCall (India): 9152987821
- Vandrevala Foundation (India): 1860-2662-345 (24/7)
- AASRA (India): 91-22-27546669

What to do in a crisis:
1. Tell someone — a friend, family member, or mental health professional.
2. Call a crisis line. They are free, confidential, and available 24/7.
3. Go to your nearest emergency department.
4. Remove access to means if you feel unsafe.
5. Stay with someone until the crisis passes.

Thoughts of suicide are symptoms of pain, not solutions. With support, the pain
can be treated. Most people who survive a suicidal crisis go on to live full lives.
        """.strip()
    },
    {
        "source": "Crisis Resources",
        "content": """
Safety planning — what to do when you feel unsafe:

A safety plan is a personalized, prioritized list of coping strategies and sources
of support that you can use when you're in crisis.

Components of a safety plan:
1. Warning signs: What thoughts, feelings, or situations signal a crisis is building?
2. Internal coping strategies: What can I do on my own to distract or soothe myself?
   (e.g., listening to music, going for a walk, breathing exercises)
3. Social contacts for distraction: Who can I contact to take my mind off things?
   (Not necessarily to discuss the crisis — just to connect)
4. People I can ask for help: Who can I talk to about what I'm experiencing?
5. Professionals/agencies to contact in crisis: Therapist, GP, crisis line numbers.
6. Making the environment safe: How can I reduce access to means?

Review and update your safety plan with a professional. Keep a copy accessible.
Share it with someone you trust.
        """.strip()
    },
    {
        "source": "Crisis Resources",
        "content": """
When to seek professional help:

See a mental health professional if:
- Symptoms have lasted more than 2 weeks
- You are missing work, school, or important activities
- Relationships are being significantly affected
- You are using alcohol or substances to cope
- You have thoughts of harming yourself or others
- You feel unable to keep yourself safe
- Self-help strategies are not working

Types of professionals:
- Psychiatrist: Medical doctor who can diagnose and prescribe medication.
- Psychologist: Trained in assessment and evidence-based therapy (CBT, DBT, etc.)
- Counselor / Therapist: Provides talk therapy and emotional support.
- GP / Family Doctor: First point of contact; can refer to specialists.

Asking for help is not a sign of weakness. It is a recognition that you deserve
support, and that professional help works. Therapy and medication (when appropriate)
are effective for the vast majority of people.
        """.strip()
    },

    # ================================================================
    # 9. MINDFULNESS
    # ================================================================
    {
        "source": "Mindfulness",
        "content": """
Mindfulness is the practice of paying attention to the present moment with
openness and without judgment. It is one of the most well-researched approaches
for reducing anxiety, depression, and stress.

Core mindfulness principles:
1. Present moment: Thoughts about the past (regret, rumination) and future (worry)
   cause most emotional suffering. Mindfulness anchors attention to now.
2. Non-judgment: Observing thoughts and feelings without labeling them as good/bad.
3. Acceptance: Allowing experiences to be as they are, without fighting or avoiding them.

Simple mindfulness practice (5 minutes):
1. Sit comfortably. Close your eyes or soften your gaze.
2. Focus attention on the physical sensations of breathing — the rise and fall of
   the belly, the air entering and leaving the nostrils.
3. When your mind wanders (and it will — this is normal), gently bring it back.
4. Each time you notice your mind has wandered and return it, that IS the practice.

Mindfulness is a skill. It gets easier and more effective with consistent practice.
Even 5 minutes daily is sufficient to see benefits within 4-8 weeks.
        """.strip()
    },
    {
        "source": "Mindfulness",
        "content": """
Mindfulness for difficult emotions — the RAIN technique:

R — Recognize: Acknowledge what you are feeling. "I notice I am feeling anxious."
    Simply naming an emotion activates the prefrontal cortex and reduces amygdala activity.

A — Allow: Let the emotion be present without trying to push it away or fix it.
    "It's okay that this is here. I can be with this."

I — Investigate: Get curious about the emotion with kindness. Where do you feel it
    in the body? What does it need? What belief is underneath it?

N — Nurture (or Non-identification): Offer yourself compassion. You are not your
    emotion — you are the awareness experiencing the emotion.
    "I am having feelings of anxiety" is different from "I am anxious."

RAIN can be used in formal meditation or in the moment when strong emotions arise.
It transforms the relationship with difficult emotions from avoidance to curious acceptance.
        """.strip()
    },

    # ================================================================
    # 10. STRESS MANAGEMENT
    # ================================================================
    {
        "source": "Stress Management",
        "content": """
Understanding stress — helpful vs. harmful:

Helpful stress (eustress): Short-term stress that motivates action — a deadline,
a performance, a challenge. The stress response is designed for this. It sharpens
focus, boosts energy, and improves performance temporarily.

Harmful stress (distress): Chronic, ongoing stress without adequate recovery.
When the stress response never fully switches off, it damages health:
- Immune suppression
- Cardiovascular damage
- Digestive problems
- Sleep disruption
- Cognitive impairment
- Increased anxiety and depression

The key is recovery. The stress response is only harmful when it becomes chronic.
Building regular recovery time into your life (rest, exercise, social connection,
sleep) is the most powerful stress management strategy.

Signs of chronic stress: Persistent tiredness, irritability, difficulty concentrating,
physical tension, getting sick frequently, feeling overwhelmed most of the time.
        """.strip()
    },
    {
        "source": "Stress Management",
        "content": """
The Stress Container model:

Imagine a container that fills up with stress. Water (stress) comes in from
life events, demands, trauma, and daily hassles. The container drains through
healthy coping — sleep, exercise, social support, therapy, relaxation.

When the container overflows, we experience psychological breakdown — anxiety,
depression, burnout, crisis.

The goal is not to eliminate stress (impossible) but to keep the container
from overflowing by increasing the size of the container (resilience) and
ensuring the drain stays open (consistent recovery practices).

Practical stress reduction:
1. Identify and reduce unnecessary stressors where possible (say no more, delegate)
2. Prioritize sleep — it is the most powerful recovery tool
3. Move your body daily — exercise metabolizes stress hormones
4. Connect socially — social support is one of the strongest buffers against stress
5. Use relaxation techniques regularly, not just in crisis
6. Consider professional support if the container is consistently overflowing
        """.strip()
    },
]


# ===================== SEEDER =====================

def seed_knowledge_base():
    """
    Ingest all KNOWLEDGE_BASE entries into rag_documents (user_id = NULL).
    Safe to run multiple times — duplicates are silently skipped.
    """
    from rag import ingest_to_rag
    import time

    total   = len(KNOWLEDGE_BASE)
    success = 0
    skipped = 0

    print(f"Seeding knowledge base: {total} entries...")

    for i, entry in enumerate(KNOWLEDGE_BASE, 1):
        result = ingest_to_rag(
            user_id    = None,
            content    = entry["content"],
            source     = entry["source"],
            session_id = None,
        )
        if result:
            success += 1
        else:
            skipped += 1

        if i % 5 == 0 or i == total:
            print(f"  Progress: {i}/{total} | success={success} skipped={skipped}")

        time.sleep(0.05)

    print(f"\nDone. Total={total} | Ingested={success} | Skipped={skipped}")


if __name__ == "__main__":
    import streamlit as st
    from ingest_documents import ensure_rag_table
    ensure_rag_table()
    seed_knowledge_base()
