import csv

def save_raw_pulses(path, rows):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['index', 'pulse'])
        for i, r in enumerate(rows):
            w.writerow([i, r])
