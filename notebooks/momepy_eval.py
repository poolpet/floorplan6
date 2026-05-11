"""momepy evaluation — Phase 2 Task 9.

Decision: NO-GO for current MVP scope.

Rationale:
  - momepy provides URBAN MORPHOLOGY metrics (circular_compactness, convexity,
    elongation) — useful for academic urban analysis or scoring sub-plot SHAPES.
  - Our Stage 1 indicators (WZ/WIZ/PBC) are simple AREA RATIOS, not shape metrics.
  - core/plot_indicators.py: ~200 lines of ratio computations. momepy would
    replace 0 lines (different problem domain).
  - Overlap analysis:
      * WZ  = footprint_area / plot_area          → plain division, no momepy API
      * WIZ = total_floor_area / plot_area         → plain division, no momepy API
      * PBC = (plot - footprint - hard) / plot     → plain subtraction + division
      * parking count                              → domain logic, unrelated to morphology
  - momepy.circular_compactness / convexity / elongation would only be useful
    for *shape-quality scoring* of generated sub-plots (Mode B), not for
    regulatory compliance indicators mandated by MPZP.
  - Revisit in Phase 4+ if/when we add shape-based scoring for Mode B sub-plot
    quality (e.g. preferring more compact sub-plots).

Eval script left below for posterity.
"""
import geopandas as gpd
from shapely.geometry import Polygon
import momepy

rect = Polygon([(0, 0), (30, 0), (30, 40), (0, 40)])
gdf = gpd.GeoDataFrame(geometry=[rect])

# circular_compactness: how close to a circle (0..1, 1 = circle)
try:
    cc = momepy.circular_compactness(gdf).iloc[0]
    print(f"circular_compactness: {cc:.3f}")
except Exception as e:
    print(f"circular_compactness API error: {e}")

# Convexity
try:
    conv = momepy.convexity(gdf).iloc[0]
    print(f"convexity: {conv:.3f}")
except Exception as e:
    print(f"convexity API error: {e}")
