import { drawCard, PITY_LIMIT } from "./draw.js";

function element<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`缺少页面元素：${id}`);
  return node as T;
}

const button = element<HTMLButtonElement>("draw");
const card = element("card");
const rarity = element("rarity");
const symbol = element("symbol");
const name = element("card-name");
const description = element("description");
const counter = element("counter");
const progress = element<HTMLProgressElement>("progress");
const status = element("status");
let misses = 0;

button.addEventListener("click", () => {
  const result = drawCard(misses);
  misses = result.misses;
  card.dataset.rarity = result.card.rarity;
  rarity.textContent = result.card.rarity;
  symbol.textContent = result.card.symbol;
  name.textContent = result.card.name;
  description.textContent = result.card.description;
  counter.textContent = String(misses);
  progress.value = misses;
  status.textContent = `${result.guaranteed ? "保底触发！" : ""}获得 ${result.card.rarity} · ${result.card.name}。${misses === 0 ? "保底计数已重置。" : `距离必得 SSR 最多还有 ${PITY_LIMIT - misses} 抽。`}`;
});
