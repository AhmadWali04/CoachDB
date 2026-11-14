// Standard full-size pitch dimensions in meters, used only for the static
// markings viewBox. Player/ball coordinates stay on the backend's 0..100
// normalized scale (frame contract, PRD §13.5) and are scaled to this box.
export const PITCH_WIDTH = 68;
export const PITCH_LENGTH = 105;

export const CENTER_CIRCLE_RADIUS = 9.15;
export const PENALTY_AREA_WIDTH = 40.32;
export const PENALTY_AREA_LENGTH = 16.5;
export const GOAL_AREA_WIDTH = 18.32;
export const GOAL_AREA_LENGTH = 5.5;
export const PENALTY_SPOT_DISTANCE = 11;
export const GOAL_WIDTH = 7.32;

const centerX = PITCH_WIDTH / 2;

export const penaltyArea = {
  x: centerX - PENALTY_AREA_WIDTH / 2,
  width: PENALTY_AREA_WIDTH,
  length: PENALTY_AREA_LENGTH,
};

export const goalArea = {
  x: centerX - GOAL_AREA_WIDTH / 2,
  width: GOAL_AREA_WIDTH,
  length: GOAL_AREA_LENGTH,
};

export const goalMouth = {
  x: centerX - GOAL_WIDTH / 2,
  width: GOAL_WIDTH,
};

export function toViewBoxX(normalizedX: number): number {
  return (normalizedX / 100) * PITCH_WIDTH;
}

export function toViewBoxY(normalizedY: number): number {
  return (normalizedY / 100) * PITCH_LENGTH;
}
