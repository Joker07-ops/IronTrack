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
        return None, "Invalid input"
    bmi = round(weight_kg / (height_m ** 2), 1)
    if bmi < 18.5:   category = "Underweight"
    elif bmi < 25:   category = "Normal"
    elif bmi < 30:   category = "Overweight"
    else:             category = "Obese"
    return bmi, category