import pandas as pd
import os
from sklearn.ensemble import IsolationForest
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
import ruptures as rpt

def analyze_df(df: pd.DataFrame, create_plots=False, output_dir='Statistics', anomaly_percentage=0.15, verbose=False):
    """
    Input:
    df: a dataframe with columns: Device, scan, procName, scan_proc_count, timestamp.
    create_plots: Boolean - if True, generates plots for each device and saves them in the output directory.
    output_dir: Directory to save plots and statistics.
    anomaly_percentage: Float between 0 and 1. Percentage of data to consider as anomalies.
    verbose: Boolean - if True, print anomaly information to console.

    Output:
    Set of anomalous devices.
    Function returns a set of statistical anomalies detected in the data.
    Computation is based on mean value and standard deviation of the difference between 
    the total process count and the scan process count for each device.
    The outliers are detected using the Isolation Forest algorithm.
    """

    # Create output directory if needed
    if create_plots:
        os.makedirs(output_dir, exist_ok=True)

    # --- Preprocessing ---
    # Count the total number of processes (i.e. if a process appears multiple times in a scan, it is multiple times)
    df['total_proc_count'] = df.groupby(['device', 'scan'])['procName'].transform('count')
    df['difference_count'] = df['total_proc_count'] - df['scan_proc_count']

    # --- Prepare data without procNames ---
    # Drop unnecessary columns and duplicates to analyze divices independently of processes
    data_no_proc = df.drop(columns=["Unnamed: 0", "procName", 'scan_proc_count', 'timestamp', 'total_proc_count']).drop_duplicates()
    # Group by device and scan to get the mean and std of difference_count
    data_no_proc['mean_difference_count'] = data_no_proc.groupby('device')['difference_count'].transform('mean')
    data_no_proc['std_difference_count'] = data_no_proc.groupby('device')['difference_count'].transform('std')

    # --- Optional: Generate Plots of difference_count per Device to analyze behavior visually  ---

    if create_plots:
        for device_name in sorted(data_no_proc['device'].unique()):
            result = data_no_proc[data_no_proc['device'] == device_name].copy()
            result.reset_index(drop=True, inplace=True)  # <--- This fixes the problem!


            if result.empty:
                continue

            result['difference_count'] = pd.to_numeric(result['difference_count'], errors='coerce')
            x_axis_col = 'scan'
            y_axis_col = 'difference_count'

            mean_value = result[y_axis_col].mean()

            plt.figure(figsize=(10, 6))

            # Plot using numeric index to align with ruptures
            plt.plot(result.index, result[y_axis_col], marker='o', label='Difference Count')

            # Plot overall mean as horizontal line
            plt.axhline(y=mean_value, color='red', linestyle='-.', label=f'Mean = {mean_value:.2f}')

            # --- Change Point Detection with ruptures ---
            signal = result[y_axis_col].dropna().values.reshape(-1, 1)

            try:
                model = "l2"
                algo = rpt.Pelt(model=model).fit(signal)
                penalty = 1000  # Try increasing for less sensitivity
                change_points = algo.predict(pen=penalty)

                # Plot vertical dashed lines for change points
                for cp in change_points[:-1]:  # skip the final boundary
                    if cp < len(result):
                        scan_label = result.iloc[cp].scan
                        plt.axvline(x=cp, color='blue', linestyle='--', alpha=0.6,
                                    label='Change Point' if cp == change_points[0] else None)
            # Handle exceptions during change point detection in case the data is not suitable
            except Exception as e:
                print(f"Skipping ruptures plot for {device_name}: {type(e).__name__} - {e}")
                plt.close()
                continue

            # Set custom x-ticks to show scan labels
            plt.xticks(ticks=result.index, labels=result['scan'], rotation=45, ha='right')

            # Formatting
            plt.title(f'Difference Count for {device_name}')
            plt.xlabel('Scan Number')
            plt.ylabel('Difference Count')
            plt.grid(True)
            plt.tight_layout()

            # Deduplicate legend entries
            handles, labels = plt.gca().get_legend_handles_labels()
            by_label = dict(zip(labels, handles))
            plt.legend(by_label.values(), by_label.keys())

            filename = os.path.join(output_dir, f'{device_name}_statistics.png')
            plt.savefig(filename)
            plt.close()

    # --- Anomaly Detection using isoluation forest on difference count mean and std
    filtered_df = data_no_proc.drop(columns=['scan', 'difference_count']).drop_duplicates()
    features = filtered_df[['mean_difference_count', 'std_difference_count']]
    iso_forest = IsolationForest(contamination=anomaly_percentage, random_state=42)
    filtered_df['anomaly'] = iso_forest.fit_predict(features)
    filtered_df['anomaly_score'] = iso_forest.decision_function(features)

    # Normalize the anomaly scores to a range of 0 to 1
    # Higher scores indicate more anomalous behavior
    scaler = MinMaxScaler()
    filtered_df['score_normalized'] = scaler.fit_transform(-filtered_df[['anomaly_score']])  # Negate to make higher = more anomalous

    # Print anomalies if verbose is True
    if verbose:
        for idx, row in filtered_df.iterrows():
            device = row['device']
            score = row['anomaly_score']
            if row['anomaly'] == -1:
                print(f"Attention: Device {device} is an anomaly (score = {score:.4f}) — needs investigation.")

    anomalous_devices = set(filtered_df.loc[filtered_df['anomaly'] == -1, 'device'])

    #Return the set of anomalous devices
    return anomalous_devices

# Example usage:
# df = pd.read_csv("synthetic_iphone_new_2.csv")
# anomalous_devices = analyze_df(df, create_plots=True, output_dir='Statistics', anomaly_percentage=0.15, verbose=True)
# print(f"Anomalous devices detected: {anomalous_devices}")
