"""Generate assets/panda_probe.xml: menagerie Panda (no hand) with a probe rod + push paddle.

Run once after cloning mujoco_menagerie:  python assets/build_panda_probe.py
The tool frame: site "tip" at the probe tip, z axis pointing out of the flange.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "mujoco_menagerie" / "franka_emika_panda" / "panda_nohand.xml"
DST = HERE / "panda_probe.xml"

# Tool frame (probe body): z points out of the flange, i.e. straight down when probing.
# Tip sphere centre at z = 0.14 (site "tip"), radius 6 mm. The paddle's bottom edge is level with the
# tip centre, so the tip sticks out 6 mm below it and touches first when probing.
# Paddle face normal is the probe's local y axis; it is 40 mm wide, 8 mm thick, 34 mm tall.
PROBE = """<site name="attachment_site"/>
                      <body name="probe" childclass="probe" gravcomp="1">
                        <geom name="probe_mount" type="cylinder" size="0.03 0.01" pos="0 0 0.01" rgba="0.2 0.2 0.2 1"/>
                        <geom name="probe_rod" type="capsule" fromto="0 0 0.02 0 0 0.134" size="0.006" rgba="0.8 0.8 0.85 1"/>
                        <geom name="paddle" type="box" size="0.02 0.004 0.017" pos="0 0 0.123" rgba="0.95 0.55 0.1 1"/>
                        <geom name="probe_tip" type="sphere" size="0.006" pos="0 0 0.14" rgba="1 0.3 0.2 1"/>
                        <site name="tip" pos="0 0 0.14" size="0.009" rgba="1 0 0 0.3" group="4"/>
                      </body>"""

DEFAULTS = """<default class="probe">
      <geom contype="1" conaffinity="1" condim="3" friction="0.4 0.005 0.0001" density="500" group="2"/>
    </default>
  </default>"""


def main() -> None:
    xml = SRC.read_text()
    xml = xml.replace('meshdir="assets"', 'meshdir="../mujoco_menagerie/franka_emika_panda/assets"')
    xml = xml.replace('<site name="attachment_site"/>', PROBE, 1)
    # Close the top-level <default> with our probe class added.
    head, sep, tail = xml.partition("\n  </default>")
    xml = head + "\n    " + DEFAULTS + tail
    # The menagerie keyframe only covers the arm's 7 dofs; the scene adds free bodies, so drop it.
    start = xml.index("<keyframe>")
    end = xml.index("</keyframe>") + len("</keyframe>")
    xml = xml[:start] + xml[end:]
    # Gravity compensation on every arm link so position actuators track without sag.
    xml = xml.replace('<body name="link', '<body gravcomp="1" name="link')
    xml = xml.replace('<mujoco model="panda nohand">', '<mujoco model="panda probe">')
    DST.write_text(xml)
    print(f"wrote {DST}")


if __name__ == "__main__":
    main()
