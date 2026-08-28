import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV data
df = pd.read_csv('aging_data.csv')

# Plot UTS vs Temperature
plt.figure(figsize=(8, 6))
plt.plot(df['aging_temperature_C'], df['UTS_MPa'], marker='o', linewidth=2)
plt.xlabel('Temperature (°C)')
plt.ylabel('UTS (MPa)')
plt.title('UTS vs Aging Temperature for Ti-6Al-4V')
plt.grid(True)
plt.tight_layout()
plt.savefig('fig_strength.png')
plt.close()

# Plot Elongation vs Temperature
plt.figure(figsize=(8, 6))
plt.plot(df['aging_temperature_C'], df['elongation_pct'], marker='o', linewidth=2)
plt.xlabel('Temperature (°C)')
plt.ylabel('Elongation (%)')
plt.title('Elongation vs Aging Temperature for Ti-6Al-4V')
plt.grid(True)
plt.tight_layout()
plt.savefig('fig_elongation.png')
plt.close()

# Find peak and valley conditions
peak_row = df.loc[df['UTS_MPa'].idxmax()]
valley_row = df.loc[df['UTS_MPa'].idxmin()]

print(f"Peak UTS: {peak_row['aging_temperature_C']}°C, {peak_row['UTS_MPa']} MPa")
print(f"Valley UTS: {valley_row['aging_temperature_C']}°C, {valley_row['UTS_MPa']} MPa")
