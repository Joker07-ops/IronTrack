from data import (
    load_workout, save_workout_exercise, delete_workout_exercise,
    load_progress, save_progress, add_to_history,
    get_history, log_workout_date, get_streak,
    get_note, save_note
)


def get_all_days(user_id):
    return list(load_workout(user_id).keys())


def get_exercises_for_day(user_id, day):
    return load_workout(user_id).get(day, [])


def add_exercise(user_id, day, exercise):
    plan = load_workout(user_id)
    if day not in plan:
        return False
    if exercise in plan[day]:
        return False
    save_workout_exercise(user_id, day, exercise)
    save_progress(user_id, day, exercise, False)
    return True


def remove_exercise(user_id, day, exercise):
    plan = load_workout(user_id)
    if day not in plan or exercise not in plan[day]:
        return False
    delete_workout_exercise(user_id, day, exercise)
    return True


def get_progress(user_id):
    return load_progress(user_id)


def mark_complete(user_id, day, exercise):
    progress = load_progress(user_id)
    if day not in progress or exercise not in progress[day]:
        return False
    save_progress(user_id, day, exercise, True)
    add_to_history(user_id, day, exercise)
    log_workout_date(user_id)
    return True


def reset_day(user_id, day):
    progress = load_progress(user_id)
    if day not in progress:
        return False
    for exercise in progress[day]:
        save_progress(user_id, day, exercise, False)
    return True


def get_summary(user_id):
    progress = load_progress(user_id)
    total = completed = 0
    day_stats = {}
    for day, exercises in progress.items():
        day_total = len(exercises)
        day_done = sum(1 for s in exercises.values() if s)
        day_stats[day] = {
            "total": day_total,
            "completed": day_done,
            "percent": round((day_done / day_total) * 100) if day_total > 0 else 0
        }
        total += day_total
        completed += day_done
    return {
        "total": total,
        "completed": completed,
        "percent": round((completed / total) * 100) if total > 0 else 0,
        "days": day_stats
    }


def calculate_bmi(weight_kg, height_m):
    if height_m <= 0 or weight_kg <= 0:
        return None, "Invalid input", None
    bmi = round(weight_kg / (height_m ** 2), 1)
    if bmi < 16:
        category = "Severely Underweight"; body_type = "Very Slim"
    elif bmi < 17.5:
        category = "Underweight"; body_type = "Slim"
    elif bmi < 18.5:
        category = "Mildly Underweight"; body_type = "Lean"
    elif bmi < 20:
        category = "Lower Normal"; body_type = "Athletic"
    elif bmi < 22.5:
        category = "Normal"; body_type = "Smart"
    elif bmi < 25:
        category = "Upper Normal"; body_type = "Fit"
    elif bmi < 27.5:
        category = "Mildly Overweight"; body_type = "Sturdy"
    elif bmi < 30:
        category = "Overweight"; body_type = "Heavy"
    elif bmi < 35:
        category = "Obese"; body_type = "Fat"
    else:
        category = "Severely Obese"; body_type = "Very Heavy"
    return bmi, category, body_type


# ── Body Shape Analysis ──────────────────────────────────────────────

def calculate_body_fat_navy(gender, age, weight_kg, height_cm, neck_cm, waist_cm, hip_cm=None):
    """Estimate body fat % using the US Navy method. Returns None if data is insufficient."""
    if gender == 'male':
        if not neck_cm or not waist_cm:
            return None
        diff = waist_cm - neck_cm
        if diff <= 0:
            return None
        bf = 495 / (1.0324 - 0.19077 * __import__('math').log10(waist_cm - neck_cm)
                      + 0.15456 * __import__('math').log10(height_cm)) - 450
    else:
        if not waist_cm or not hip_cm:
            return None
        diff = waist_cm + hip_cm
        if diff <= 0:
            return None
        bf = 495 / (1.29579 - 0.35004 * __import__('math').log10(waist_cm + hip_cm)
                      + 0.22100 * __import__('math').log10(height_cm)) - 450
    return round(max(2, min(bf, 60)), 1)


def calculate_whr(waist_cm, hip_cm):
    """Calculate Waist-to-Hip Ratio."""
    if not hip_cm or hip_cm <= 0 or not waist_cm or waist_cm <= 0:
        return None
    return round(waist_cm / hip_cm, 3)


def classify_body_shape(gender, waist_cm, hip_cm, shoulder_cm, whr=None):
    """Classify body shape based on measurements. Returns (shape_name, description)."""
    if not waist_cm or not hip_cm:
        return None, None

    if not whr:
        whr = waist_cm / hip_cm if hip_cm > 0 else 0

    # Ratios
    waist_hip_diff = waist_cm - hip_cm
    waist_hip_ratio = whr
    shoulder_hip_ratio = (shoulder_cm / hip_cm) if shoulder_cm and hip_cm > 0 else None

    if gender == 'male':
        # Male body shapes
        if shoulder_hip_ratio and shoulder_hip_ratio > 1.15:
            if waist_cm < hip_cm * 0.9:
                return 'inverted_triangle', (
                    'Inverted Triangle (V-Shape)',
                    'Your shoulders are significantly wider than your hips with a tapered waist. '
                    'You naturally carry more muscle in your upper body.'
                )
            else:
                return 'inverted_triangle', (
                    'Inverted Triangle (V-Shape)',
                    'Your shoulders are notably broader than your hips. '
                    'Your upper body is naturally more developed.'
                )
        elif whr < 0.85:
            return 'triangle', (
                'Triangle (Pear)',
                'Your hips are wider than your shoulders. '
                    'You tend to carry more weight in your lower body.'
            )
        elif waist_hip_ratio < 0.9 and shoulder_hip_ratio and abs(shoulder_hip_ratio - 1.0) < 0.1:
            return 'hourglass', (
                'Hourglass',
                'Your shoulders and hips are roughly equal with a defined waist. '
                'You have a balanced, proportional build.'
            )
        elif waist_cm > hip_cm * 1.0:
            return 'apple', (
                'Apple (Round)',
                'Your waist is wider than or equal to your hips. '
                'You tend to carry weight around your midsection.'
            )
        else:
            return 'rectangle', (
                'Rectangle (Straight)',
                'Your shoulders, waist, and hips are roughly proportional. '
                'You have a balanced, athletic build.'
            )
    else:
        # Female body shapes
        if waist_hip_ratio < 0.75 and shoulder_hip_ratio and abs(shoulder_hip_ratio - 1.0) < 0.1:
            return 'hourglass', (
                'Hourglass',
                'Your shoulders and hips are nearly equal with a well-defined waist. '
                'You have a balanced, proportional figure.'
            )
        elif hip_cm > shoulder_cm * 1.05 and waist_hip_ratio < 0.8:
            return 'pear', (
                'Pear (Triangle)',
                'Your hips are wider than your shoulders with a defined waist. '
                'You carry more weight in your hips, thighs, and buttocks.'
            )
        elif waist_cm > hip_cm * 0.85 or (shoulder_hip_ratio and shoulder_hip_ratio > 1.1):
            return 'apple', (
                'Apple (Round)',
                'Your waist is relatively wide compared to your hips. '
                'You tend to carry weight around your midsection.'
            )
        elif waist_hip_ratio > 0.75 and waist_hip_ratio < 0.85 and shoulder_hip_ratio and abs(shoulder_hip_ratio - 1.0) < 0.15:
            return 'rectangle', (
                'Rectangle (Straight)',
                'Your shoulders, waist, and hips are fairly proportional. '
                'You have an athletic, streamlined silhouette.'
            )
        elif shoulder_hip_ratio and shoulder_hip_ratio > 1.1:
            return 'inverted_triangle', (
                'Inverted Triangle',
                'Your shoulders are broader than your hips. '
                'You carry more weight in your upper body.'
            )
        else:
            return 'rectangle', (
                'Rectangle (Straight)',
                'Your measurements are fairly balanced across shoulders, waist, and hips. '
                'You have a straight, athletic build.'
            )


BODY_SHAPE_TIPS = {
    'hourglass': {
        'focus': 'Balanced full-body training',
        'avoid': 'Over-emphasizing one area at the expense of balance',
        'ideal': 'Compound movements that maintain your natural proportions',
    },
    'pear': {
        'focus': 'Upper body strengthening + lower body toning',
        'avoid': 'Excessive lower-body heavy loads without upper body balance',
        'ideal': 'Shoulder/back exercises to balance proportions, glute isolation for tone',
    },
    'apple': {
        'focus': 'Core stability + overall fat reduction',
        'avoid': 'Heavy midsection loading, excessive direct ab work without fat loss',
        'ideal': 'Cardio, full-body compound lifts, core stabilization (planks, dead bugs)',
    },
    'rectangle': {
        'focus': 'Building curves through targeted hypertrophy',
        'avoid': 'Staying in a caloric deficit too long, only doing cardio',
        'ideal': 'Progressive overload on compound lifts, shoulder/hip/glute isolation',
    },
    'inverted_triangle': {
        'focus': 'Lower body volume + core + back width',
        'avoid': 'Over-training shoulders/chest (already dominant)',
        'ideal': 'Squats, lunges, glute bridges, lateral raises (moderate), rows',
    },
    'triangle': {
        'focus': 'Upper body volume + lower body toning',
        'avoid': 'Excessive lower-body heavy training that increases hip width further',
        'ideal': 'Overhead press, pull-ups, rows, hip thrusters (moderate weight)',
    },
}