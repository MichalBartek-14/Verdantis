"""
Client-facing chart/map generation. Deliberately simple matplotlib output
(PNG) for the pilot stage - swap in a proper report template later.
"""
import matplotlib.pyplot as plt
import numpy as np


def plot_ndvi_timeseries(dates, values, out_path, title="Plot-average NDVI - monthly composites"):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dates, values, marker="o", linewidth=1.5, color="#2c7a3c")
    ax.set_ylabel("Mean NDVI")
    ax.set_xlabel("Month")
    ax.set_title(title)
    ax.set_ylim(-0.1, 1.0)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_dryness_heatmap(frequency_array, out_path, title="Frequency of 'dry' pixels (NDWI-based)"):
    fig, ax = plt.subplots(figsize=(7, 7))
    im = ax.imshow(frequency_array, cmap="YlOrRd", vmin=0, vmax=100)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("% of valid months classified 'dry'")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ndwi_timeseries(dates, values, out_path, title="Plot-average NDWI - monthly composites"):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dates, values, marker="o", linewidth=1.5, color="#1f7a8c")
    ax.axhline(0, color="#999999", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Mean NDWI")
    ax.set_xlabel("Month")
    ax.set_title(title)
    ax.set_ylim(-0.3, 0.3)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ndmi_timeseries(dates, values, out_path, title="Plot-average NDMI - monthly composites"):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(dates, values, marker="o", linewidth=1.5, color="#8a6d3b")
    ax.axhline(0, color="#999999", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Mean NDMI")
    ax.set_xlabel("Month")
    ax.set_title(title)
    ax.set_ylim(-0.3, 0.3)
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_water_loss_map(frequency_array, magnitude_array, out_path,
                         title="Where the plot loses vegetation water most", index_name="NDWI"):
    """Two-panel map: how OFTEN each pixel ran dry (% of valid months,
    left) next to HOW MUCH moisture it typically lost when it did (mean
    deficit below the dry threshold, right, for whichever moisture index
    `index_name` names) - frequency and severity side by side over the
    full historical window."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))

    im0 = axes[0].imshow(frequency_array, cmap="YlOrRd", vmin=0, vmax=100)
    axes[0].set_title("How often (% of months classified 'dry')")
    axes[0].set_xticks([])
    axes[0].set_yticks([])
    cbar0 = fig.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)
    cbar0.set_label("% of valid months dry")

    finite_magnitude = magnitude_array[np.isfinite(magnitude_array)]
    vmax_mag = float(finite_magnitude.max()) if finite_magnitude.size else 0.01
    im1 = axes[1].imshow(magnitude_array, cmap="YlOrBr", vmin=0, vmax=max(vmax_mag, 0.01))
    axes[1].set_title(f"How much (mean {index_name} deficit when dry)")
    axes[1].set_xticks([])
    axes[1].set_yticks([])
    cbar1 = fig.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)
    cbar1.set_label(f"Mean {index_name} below threshold")

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ndwi_temperature_combo(months, ndwi_values, temp_values, out_path,
                                 title="Monthly NDWI vs. ERA5 mean temperature"):
    """Dual-axis chart: plot-average NDWI (left axis) against ERA5 mean
    monthly air temperature (right axis) over the same months, to
    visually check whether moisture drops track warm spells."""
    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    ax1.plot(months, ndwi_values, marker="o", linewidth=1.5, color="#1f7a8c", label="Mean NDWI")
    ax1.set_ylabel("Mean NDWI", color="#1f7a8c")
    ax1.tick_params(axis="y", labelcolor="#1f7a8c")
    ax1.set_xlabel("Month")
    ax1.grid(alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(months, temp_values, marker="s", linewidth=1.5, color="#d1495b", label="Mean temperature (ERA5)")
    ax2.set_ylabel("Mean temperature (°C, ERA5)", color="#d1495b")
    ax2.tick_params(axis="y", labelcolor="#d1495b")

    ax1.set_title(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_bfast_breaks(raw_series, trend_index, trend_values, break_dates, out_path,
                       title="NDVI - every available scene, with detected structural breaks"):
    """Raw per-scene NDVI (every available Sentinel-2 acquisition over the
    alert bbox, not a monthly/weekly composite) as a scatter, the STL
    trend fitted for break detection as a line, and each detected
    break marked with a vertical dashed line - the alert branch's core
    chart."""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.scatter(raw_series.index, raw_series.values, s=14, color="#7a8c9e", alpha=0.6, label="Raw scene NDVI")
    ax.plot(trend_index, trend_values, color="#2c7a3c", linewidth=1.8, label="STL trend")
    for i, bd in enumerate(break_dates):
        ax.axvline(bd, color="#c0392b", linestyle="--", linewidth=1.2,
                    label="Detected break" if i == 0 else None)
    ax.set_ylabel("NDVI")
    ax.set_xlabel("Date")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_index_quicklook(array, out_path, cmap, vmin, vmax, title, cbar_label):
    """Single-band colorized PNG quicklook for one index composite -
    lets a per-date output folder be browsed/previewed directly in a
    normal file explorer, without needing GIS software to open the
    paired GeoTIFF."""
    fig, ax = plt.subplots(figsize=(6, 6))
    im = ax.imshow(array, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
