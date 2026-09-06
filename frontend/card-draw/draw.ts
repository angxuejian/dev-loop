export type Rarity = "R" | "SR" | "SSR";

export interface Card {
  name: string;
  rarity: Rarity;
  symbol: string;
  description: string;
}

export const cardPool: Record<Rarity, readonly Card[]> = {
  R: [
    {
      name: "林间信使",
      rarity: "R",
      symbol: "❧",
      description: "沿着风的方向，送来森林的问候。",
    },
    {
      name: "月光旅人",
      rarity: "R",
      symbol: "☾",
      description: "每一步，都有微光相伴。",
    },
  ],
  SR: [
    {
      name: "星辰守望者",
      rarity: "SR",
      symbol: "✧",
      description: "守护长夜中不曾熄灭的星辰。",
    },
    {
      name: "晨曦术士",
      rarity: "SR",
      symbol: "☀",
      description: "将第一缕晨光，化作掌心的魔法。",
    },
  ],
  SSR: [
    {
      name: "永恒星辉",
      rarity: "SSR",
      symbol: "✦",
      description: "跨越漫长星河，终于与你相遇。",
    },
    {
      name: "命运织者",
      rarity: "SSR",
      symbol: "✴",
      description: "万千可能，在此刻交汇。",
    },
  ],
};

export const PITY_LIMIT = 50;

export function drawCard(misses: number, random: () => number = Math.random) {
  if (!Number.isInteger(misses) || misses < 0 || misses >= PITY_LIMIT) {
    throw new RangeError("保底计数必须是 0 到 49 的整数");
  }
  const guaranteed = misses === PITY_LIMIT - 1;
  const roll = guaranteed ? 1 : random();
  const rarity: Rarity = roll < 0.8 ? "R" : roll < 0.98 ? "SR" : "SSR";
  const cards = cardPool[rarity];
  const card = cards[Math.floor(random() * cards.length)];
  return { card, misses: rarity === "SSR" ? 0 : misses + 1, guaranteed };
}
