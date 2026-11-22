import { isPushing, type SimState } from "@/lib/sim";

export type Tone = "info" | "good" | "alert" | "think";

export interface Narration {
  title: string;
  body: string;
  tone: Tone;
}

/** The newest event's text and age (sim seconds), e.g. "[ 187.3s] route check: ..." */
function latestEvent(s: SimState): { text: string; age: number } | null {
  const e = s.events.at(-1);
  if (!e) return null;
  const m = e.match(/^\[\s*([\d.]+)s\]\s*(.*)$/);
  if (!m) return { text: e, age: 0 };
  return { text: m[2], age: s.t - Number(m[1]) };
}

/** One plain-language sentence about what the robot is doing right now, and why. */
export function narrate(s: SimState | null, connected: boolean | null): Narration {
  if (connected === false)
    return { title: "Waiting for the simulation", body: "Start the sim server and this page connects on its own.", tone: "alert" };
  if (!s) return { title: "Connecting…", body: "Loading the robot's world.", tone: "info" };
  if (!s.auto) return { title: "Paused", body: "Press Run in the top bar to continue.", tone: "info" };

  const ev = latestEvent(s);
  const recent = ev && ev.age < 6 ? ev.text : "";
  const push = isPushing(s);
  const lastPush = s.pushes.at(-1);

  // Moments worth calling out, newest first.
  if (/CHANGE CONFIRMED/.test(recent))
    return { title: "Something moved — confirmed", body: "A spot it touched earlier feels different now, so it forgets the out-of-date touches around it and maps that area again.", tone: "alert" };
  if (/surprise/.test(recent))
    return { title: "That didn't feel right…", body: "This touch doesn't match the map. Before trusting it, the robot re-touches a nearby spot it knows, to check whether something really moved.", tone: "alert" };
  if (/physics changed|missed (its )?prediction/.test(recent) || (push && lastPush?.change && ev && ev.age < 6))
    return { title: "The puck didn't go where it expected!", body: `It missed its own prediction by ${lastPush?.miss_cm?.toFixed(1) ?? "several"} cm — the physics must have changed. It drops its old push experience and relearns from the next few pushes.`, tone: "alert" };
  if (/route check: something/.test(recent))
    return { title: "Found an obstacle by touch", body: "Something tall is on the puck's route — the map didn't know yet. It plans a different push around it.", tone: "alert" };
  if (/map done/.test(recent))
    return { title: "Map finished — now pushing", body: "It has felt enough of the table. Next it pushes the puck to the green goal, avoiding the boxes it found.", tone: "good" };
  if (/PRESENTER/.test(recent))
    return { title: "The presenter changed something", body: recent.replace(/^PRESENTER:\s*/, "") + ". The robot isn't told — it has to notice by itself.", tone: "info" };

  if (push) {
    const st = s.push_status || "";
    if (st.startsWith("at goal"))
      return { title: "Goal reached!", body: "Give it a new target: click the green goal in the view, then click anywhere on the table.", tone: "good" };
    if (st.startsWith("no safe push"))
      return { title: "Stuck: no safe push", body: "Every push it considers would hit a box or leave the table. Move the puck or the goal to help it.", tone: "alert" };
    if (st.startsWith("puck out of reach"))
      return { title: "Puck out of reach", body: "Click the red puck, then click a spot on the table to put it back.", tone: "alert" };
    if (st.startsWith("lost the puck"))
      return { title: "Lost the puck", body: "It felt everywhere the puck could be and didn't find it. Click the red puck, then a spot on the table, to tell it where the puck is.", tone: "alert" };
    if (st.startsWith("feeling for the puck: not where"))
      return { title: "The puck isn't where it predicted", body: "Its touches came up empty where the model said the puck would stop, so it searches wider. Finding it far away is how it notices the physics changed.", tone: "alert" };
    if (st.startsWith("feeling for the puck"))
      return { title: "Feeling for the puck", body: `It can't see where the puck stopped, so it touches where TabPFN predicts it should be. Each touch rules out half the remaining spots; the better the model, the fewer touches it needs.${lastPush?.search_touches != null ? ` Last time: ${lastPush.search_touches} touches.` : ""}`, tone: "think" };
    if (st.startsWith("checking the route"))
      return { title: "Feeling the route before pushing", body: "The map is only as fresh as its last touch, so it taps along the puck's path to make sure nothing moved there.", tone: "think" };
    if (st.startsWith("seed push"))
      return { title: "Learning how the puck moves", body: "No experience yet, so it makes a few gentle test pushes. Each one becomes a row of data for TabPFN.", tone: "think" };
    if (st.startsWith("planning"))
      return { title: "Choosing the next push", body: "TabPFN predicts where hundreds of possible pushes would send the puck — with error bars — and the robot picks the safest one that ends nearest the goal.", tone: "think" };
    if (st.startsWith("pushing"))
      return { title: "Pushing", body: "Afterwards it compares where the puck stopped with where it predicted. A big miss means the world changed.", tone: "info" };
    return { title: "Pushing the puck to the goal", body: "Every push teaches it a little more about how the puck slides.", tone: "info" };
  }

  if (s.probes < 5)
    return { title: "Starting blind", body: "The robot can't see. It knows nothing about the table yet, so it starts by touching a few spots.", tone: "think" };
  return {
    title: "Touching where it's least sure",
    body: `${s.probes} touches so far. After each one, TabPFN redraws the whole map in about a second — no training. Faded tiles are where it's still unsure; that's where it touches next.`,
    tone: "think",
  };
}
