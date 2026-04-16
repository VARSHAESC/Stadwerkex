import pandas as pd
import numpy as np
import datetime

# Define columns based on the Soll-Profil and user questions
columns = [
    'Objekt-ID', 'Gemeinde', 'Ortsteil', 'Straße', 'Hausnummer', 
    'Breitengrad', 'Längengrad', 'Anschlussart', 'Baujahr', 
    'Material', 'Dimension', 'Länge (m)', 
    'Plan_vorhanden', 'Abnahmeprotokoll_vorhanden', 'Materialangaben_vorhanden',
    'Störungshistorie (Anzahl)', 'Zustand', 'Wärmepumpe_geeignet', 
    'Ladeinfrastruktur_geeignet', 'Letzte_Prüfung', 'Nächste_Prüfung', 
    'Erneuerung_Jahr'
]

n = 50
np.random.seed(42)

data = {
    'Objekt-ID': [f'OBJ-{1000+i}' for i in range(n)],
    'Gemeinde': ['Düsseldorf'] * n,
    'Ortsteil': np.random.choice(['Zentrum', 'Nord', 'Süd', 'West', 'Ost'], n),
    'Straße': np.random.choice(['Hauptstraße', 'Nebenweg', 'Energieallee', 'Kundenpfad', 'Netzweg', 'Stromgasse', 'Gasring'], n),
    'Hausnummer': np.random.randint(1, 150, n),
    'Breitengrad': np.random.uniform(51.2, 51.3, n),
    'Längengrad': np.random.uniform(6.7, 6.8, n),
    'Anschlussart': np.random.choice(['Strom', 'Gas', 'Wasser'], n),
    'Baujahr': np.random.randint(1960, 2024, n),
    'Material': np.random.choice(['PE', 'HDPE', 'Gusseisen', 'Stahl', 'Kupfer', 'PVC'], n),
    'Dimension': np.random.choice(['DN25', 'DN32', 'DN40', 'DN50', 'DN100'], n),
    'Länge (m)': np.random.randint(5, 50, n),
    'Plan_vorhanden': np.random.choice(['Ja', 'Nein'], n, p=[0.7, 0.3]),
    'Abnahmeprotokoll_vorhanden': np.random.choice(['Ja', 'Nein'], n, p=[0.6, 0.4]),
    'Materialangaben_vorhanden': np.random.choice(['Ja', 'Nein'], n, p=[0.8, 0.2]),
    'Störungshistorie (Anzahl)': np.random.poisson(0.5, n),
    'Zustand': np.random.choice(['Gut', 'Mittel', 'Schlecht'], n, p=[0.6, 0.3, 0.1]),
    'Wärmepumpe_geeignet': np.random.choice(['Ja', 'Nein', 'Bedingt'], n),
    'Ladeinfrastruktur_geeignet': np.random.choice(['Ja', 'Nein', 'Bedingt'], n),
    'Letzte_Prüfung': [datetime.date(2020 + np.random.randint(0, 5), np.random.randint(1, 13), np.random.randint(1, 28)) for _ in range(n)],
}

df = pd.DataFrame(data)

# Add logic-based columns
df['Alter'] = 2024 - df['Baujahr']
df['Nächste_Prüfung'] = df['Letzte_Prüfung'] + pd.to_timedelta(np.random.randint(365, 365*5, n), unit='D')
df['Erneuerung_Jahr'] = df['Baujahr'] + np.where(df['Material'] == 'Gusseisen', 40, 60)
df.loc[df['Zustand'] == 'Schlecht', 'Erneuerung_Jahr'] = 2024 + np.random.randint(0, 3, df[df['Zustand'] == 'Schlecht'].shape[0])

# Save as the new reference file
df.to_excel("excel_data/Hausanschluss_Data_Actual.xlsx", index=False)
print("Saved 50 records to excel_data/Hausanschluss_Data_Actual.xlsx")
