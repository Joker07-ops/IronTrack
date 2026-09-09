"""
Preset workout program templates.
All exercise names match exercises.py EXERCISES dict so every
exercise has full hardcoded details (how-to, benefits, video) —
no AI generation needed for any template exercise.
"""

WORKOUT_TEMPLATES = {

    "classic": {
        "name": "Classic Full Week",
        "icon": "calendar",
        "level": "Beginner",
        "days_count": 9,
        "description": "The default IronTrack plan — one focused muscle group per day across a 9-day rotation, plus a dedicated cardio day.",
        "plan": {
            "Day 1 (Chest)":       ["Push-ups", "Bench Press", "Chest Fly"],
            "Day 2 (Legs)":        ["Squats", "Lunges", "Leg Press"],
            "Day 3 (Back)":        ["Pull-ups", "Deadlift", "Lat Pulldown"],
            "Day 4 (Shoulders)":   ["Shoulder Press", "Lateral Raises", "Shrugs"],
            "Day 5 (Arms)":        ["Bicep Curls", "Tricep Dips", "Hammer Curls"],
            "Day 6 (Core)":        ["Plank", "Crunches", "Leg Raises"],
            "Day 7 (Rest)":        ["Rest Day - Light Stretching / Recovery"],
            "Day 8 (Full Body)":   ["Burpees", "Mountain Climbers", "Jumping Jacks"],
            "Day Special (Cardio)": ["Running", "Cycling", "Jump Rope"],
        }
    },

    "ppl": {
        "name": "Push / Pull / Legs",
        "icon": "refresh-cw",
        "level": "Intermediate",
        "days_count": 7,
        "description": "A 6-day split rotating Push, Pull, and Leg days twice per week — high training frequency for faster muscle growth.",
        "plan": {
            "Day 1 (Push A)":  ["Bench Press", "Shoulder Press", "Chest Fly", "Tricep Dips"],
            "Day 2 (Pull A)":  ["Pull-ups", "Deadlift", "Lat Pulldown", "Bicep Curls"],
            "Day 3 (Legs A)":  ["Squats", "Lunges", "Leg Press", "Leg Raises"],
            "Day 4 (Push B)":  ["Push-ups", "Lateral Raises", "Shoulder Press", "Tricep Dips"],
            "Day 5 (Pull B)":  ["Lat Pulldown", "Hammer Curls", "Shrugs", "Deadlift"],
            "Day 6 (Legs B)":  ["Squats", "Leg Press", "Plank", "Crunches"],
            "Day 7 (Rest)":    ["Rest Day - Light Stretching / Recovery"],
        }
    },

    "upper_lower": {
        "name": "Upper / Lower Split",
        "icon": "arrow-up-down",
        "level": "Intermediate",
        "days_count": 6,
        "description": "A 4-day split alternating Upper and Lower body sessions, with a rest day and a dedicated cardio day built in.",
        "plan": {
            "Day 1 (Upper A)": ["Bench Press", "Lat Pulldown", "Shoulder Press", "Bicep Curls"],
            "Day 2 (Lower A)": ["Squats", "Lunges", "Leg Press", "Leg Raises"],
            "Day 3 (Upper B)": ["Push-ups", "Pull-ups", "Lateral Raises", "Tricep Dips"],
            "Day 4 (Lower B)": ["Deadlift", "Leg Press", "Plank", "Crunches"],
            "Day 5 (Rest)":    ["Rest Day - Light Stretching / Recovery"],
            "Day 6 (Cardio)":  ["Running", "Cycling", "Jump Rope"],
        }
    },

    "full_body": {
        "name": "Full Body 3-Day",
        "icon": "repeat",
        "level": "Beginner",
        "days_count": 5,
        "description": "Three full-body sessions per week that train every major muscle group — ideal for beginners or anyone with limited gym time.",
        "plan": {
            "Day 1 (Full Body A)": ["Squats", "Bench Press", "Pull-ups", "Plank"],
            "Day 2 (Full Body B)": ["Deadlift", "Shoulder Press", "Lat Pulldown", "Crunches"],
            "Day 3 (Full Body C)": ["Lunges", "Push-ups", "Bicep Curls", "Leg Raises"],
            "Day 4 (Rest)":        ["Rest Day - Light Stretching / Recovery"],
            "Day 5 (Cardio)":      ["Running", "Cycling", "Jump Rope"],
        }
    },

}