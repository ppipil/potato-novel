<script setup>
// 隐藏工作台页面面向内部编辑流程：负责把大纲解析成节点图、补写单节点，并把编辑后的故事包导入书市。
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  completeLibraryWorkbenchNode,
  deleteImportedLibraryStory,
  importLibraryStoryPackage,
  parseLibraryWorkbenchOutline,
} from "../lib/api";
import { readLibraryStoriesCache, writeLibraryStoriesCache } from "../lib/storyCache";

const router = useRouter();
const FORCE_REFRESH_LIBRARY_KEY = "potato-novel-force-refresh-library";
const WORKBENCH_LAYOUT_KEY = "potato-novel-workbench-layout-v1";
const WORKBENCH_NODE_POSITIONS_KEY = "potato-novel-workbench-node-positions-v1";
const MIN_CHOICES = 2;
const MAX_CHOICES = 4;
const CHOICE_LABELS = ["A", "B", "C", "D"];

const importing = ref(false);
const deleting = ref(false);
const aiWorking = ref(false);
const parseWorking = ref(false);
const loadingRows = ref(false);
const libraryRows = ref([]);
const selectedNodeId = ref("N1");
const error = ref("");
const success = ref("");
const deleteReceipt = ref(null);
const desktopLayout = ref(false);
const canvasBoardRef = ref(null);
const nodePositionOverrides = ref({});
const dragState = ref(null);
const connectionState = ref(null);
const blockNodeClickUntil = ref(0);

const form = ref({
  storyId: "",
  title: "",
  opening: "",
  summary: "",
  sortOrder: "",
  role: "主人公",
  provider: "volcengine",
  outlineText: "",
});

const storyPackage = ref(createStarterPackage());

const shellClass = computed(() => (desktopLayout.value ? "workbench-shell-desktop" : "paper-shell"));
const pageClass = computed(() =>
  desktopLayout.value
    ? "paper-page min-h-screen px-5 py-6 sm:px-8 lg:px-10"
    : "paper-page min-h-screen px-5 py-6 sm:px-8"
);
const contentClass = computed(() => (desktopLayout.value ? "mx-auto max-w-[96rem] space-y-6" : "mx-auto max-w-[39rem] space-y-5"));

function toNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function safeText(value) {
  return String(value || "").trim();
}

function deepClone(payload) {
  return JSON.parse(JSON.stringify(payload));
}

function clampChoiceCount(rawValue, fallback = 3) {
  const value = Math.floor(toNumber(rawValue, fallback));
  if (value < MIN_CHOICES) {
    return MIN_CHOICES;
  }
  if (value > MAX_CHOICES) {
    return MAX_CHOICES;
  }
  return value;
}

function parseSortOrder(value) {
  const trimmed = safeText(value);
  if (!trimmed) {
    return undefined;
  }
  const num = Number(trimmed);
  return Number.isFinite(num) ? Math.floor(num) : undefined;
}

function loadWorkbenchLayoutPreference() {
  try {
    desktopLayout.value = localStorage.getItem(WORKBENCH_LAYOUT_KEY) === "desktop";
  } catch {
    desktopLayout.value = false;
  }
}

function persistWorkbenchLayoutPreference() {
  try {
    localStorage.setItem(WORKBENCH_LAYOUT_KEY, desktopLayout.value ? "desktop" : "mobile");
  } catch {
    // ignore localStorage errors
  }
}

function toggleWorkbenchLayout() {
  desktopLayout.value = !desktopLayout.value;
  persistWorkbenchLayoutPreference();
}

function parseNodePositionOverrides(rawValue) {
  const source = rawValue && typeof rawValue === "object" ? rawValue : {};
  const result = {};
  for (const [nodeId, point] of Object.entries(source)) {
    if (!nodeId || !point || typeof point !== "object") {
      continue;
    }
    const x = Number(point.x);
    const y = Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      continue;
    }
    result[nodeId] = {
      x: Math.max(20, Math.round(x)),
      y: Math.max(46, Math.round(y)),
    };
  }
  return result;
}

function loadNodePositionOverrides() {
  try {
    const raw = localStorage.getItem(WORKBENCH_NODE_POSITIONS_KEY);
    if (!raw) {
      nodePositionOverrides.value = {};
      return;
    }
    nodePositionOverrides.value = parseNodePositionOverrides(JSON.parse(raw));
  } catch {
    nodePositionOverrides.value = {};
  }
}

function persistNodePositionOverrides() {
  try {
    localStorage.setItem(WORKBENCH_NODE_POSITIONS_KEY, JSON.stringify(nodePositionOverrides.value || {}));
  } catch {
    // ignore localStorage errors
  }
}

function clearDanglingNodePositionOverrides(validNodeIds) {
  const next = {};
  let changed = false;
  for (const [nodeId, point] of Object.entries(nodePositionOverrides.value || {})) {
    if (!validNodeIds.has(nodeId)) {
      changed = true;
      continue;
    }
    next[nodeId] = point;
  }
  if (changed) {
    nodePositionOverrides.value = next;
    persistNodePositionOverrides();
  }
}

function cubicPointAt(t, p0, p1, p2, p3) {
  const it = 1 - t;
  return (
    it ** 3 * p0 +
    3 * it ** 2 * t * p1 +
    3 * it * t ** 2 * p2 +
    t ** 3 * p3
  );
}

function createBezierPath(from, to) {
  const distance = Math.abs(to.x - from.x);
  const bend = Math.max(52, Math.min(188, distance * 0.55));
  const c1 = { x: from.x + bend, y: from.y };
  const c2 = { x: to.x - bend, y: to.y };
  const mid = {
    x: cubicPointAt(0.5, from.x, c1.x, c2.x, to.x),
    y: cubicPointAt(0.5, from.y, c1.y, c2.y, to.y),
  };
  return {
    path: `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`,
    mid,
  };
}

function getNodeInputPoint(layoutNode) {
  return {
    x: layoutNode.x - 8,
    y: layoutNode.y + layoutNode.height / 2,
  };
}

function getChoiceOutputPoint(layoutNode, choiceIndex, totalChoices) {
  const safeCount = Math.max(1, totalChoices);
  if (safeCount === 1) {
    return {
      x: layoutNode.x + layoutNode.width + 8,
      y: layoutNode.y + layoutNode.height / 2,
    };
  }
  const top = layoutNode.y + 24;
  const bottom = layoutNode.y + layoutNode.height - 18;
  const step = (bottom - top) / (safeCount - 1);
  return {
    x: layoutNode.x + layoutNode.width + 8,
    y: top + step * choiceIndex,
  };
}

function buildDefaultInitialState() {
  return {
    stage: "opening",
    flags: [],
    relationship: {
      favor: 0,
      taiziFavor: 30,
      chuxiangFavor: 20,
      peijiFavor: 20,
      generalFavor: 20,
      revealRisk: 15,
      peijiControl: 10,
      powerBias: 0,
      darkness: 0,
    },
    persona: {
      extrovert_introvert: 0,
      scheming_naive: 0,
      optimistic_pessimistic: 0,
    },
    turn: 1,
    endingHint: "",
  };
}

function createChoice(nodeId, index, nextNodeId, text = "", style = "dialogue", tone = "生活化", effects = {}) {
  return {
    id: `${nodeId}-C${index}`,
    text,
    nextNodeId,
    style,
    tone,
    effects: {
      persona: {
        ...(effects?.persona || {}),
      },
      relationship: {
        ...(effects?.relationship || {}),
      },
    },
  };
}

function createEndingNode(id, summary, scene, endingType = "open") {
  return {
    id,
    kind: "ending",
    turn: 7,
    stageLabel: "结局",
    directorNote: "",
    summary,
    scene,
    endingType,
    choiceCount: 0,
    choices: [],
  };
}

function createStarterPackage() {
  return {
    version: 2,
    generatedBy: "library_workbench_studio_v1",
    title: "未命名互动宇宙",
    opening: "请在这里输入你的故事开头",
    role: "主人公",
    rootNodeId: "N1",
    initialState: buildDefaultInitialState(),
    nodes: [
      {
        id: "N1",
        kind: "turn",
        turn: 1,
        stageLabel: "第一幕",
        directorNote: "把冲突抛出来，让读者立刻想选。",
        summary: "主角遭遇突发局面，必须马上回应。",
        scene: "",
        choiceCount: 3,
        choices: [
          createChoice("N1", 1, "N2"),
          createChoice("N1", 2, "N2"),
          createChoice("N1", 3, "N2"),
        ],
      },
      {
        id: "N2",
        kind: "turn",
        turn: 2,
        stageLabel: "第二幕",
        directorNote: "让剧情升温，准备进入不同收束。",
        summary: "第二次抉择决定最终走向。",
        scene: "",
        choiceCount: 3,
        choices: [
          createChoice("N2", 1, "E-sweet"),
          createChoice("N2", 2, "E-open"),
          createChoice("N2", 3, "E-cold"),
        ],
      },
      createEndingNode("E-sweet", "甜系结局", "", "good"),
      createEndingNode("E-open", "开放结局", "", "open"),
      createEndingNode("E-cold", "冷感结局", "", "bittersweet"),
    ],
  };
}

function createImperialOutlinePackage() {
  const pkg = {
    version: 2,
    generatedBy: "imperial-chaos-outline-v1",
    title: "东宫翻车：马车掉马后全员失控",
    opening: "太子捏着你昨夜的香囊，笑意却冷得像刀。你才意识到，自己在东宫、丞相府与将军府之间多线周旋的事，今晚可能全盘翻车。",
    role: "伪装成太监的女主",
    rootNodeId: "N1",
    initialState: buildDefaultInitialState(),
    nodes: [
      {
        id: "N1",
        kind: "turn",
        turn: 1,
        stageLabel: "Chapter 1 · 东宫翻车",
        directorNote: "太子已起疑，修罗场导火索点燃。",
        summary: "太子发现你多线操作，压迫感拉满。A/B 刷好感，C 推主线。",
        scene: "太子把香囊压在桌角，指尖一点点摩挲着绣线。殿门都关了，你却听见风声从背后刮过来。他笑着问你昨夜去了哪里，语气温柔，眼神却像在量刑。你知道，今夜任何一句话都可能把自己送进局里。",
        choiceCount: 3,
        choices: [
          createChoice("N1", 1, "N1-soft", "我先低头认错，轻声哄他，说只是怕他太累才没敢打扰。", "soft", "温柔", { relationship: { favor: 1, taiziFavor: 18, revealRisk: -4 } }),
          createChoice("N1", 2, "N1-flirt", "我靠近半步反撩他，笑着问太子殿下这是吃醋了吗？", "tease", "撩拨", { relationship: { favor: 1, taiziFavor: 10, revealRisk: 8 } }),
          createChoice("N1", 3, "N2", "我反向甩锅，说是东宫内侍故意传错消息逼我出宫。", "strategy", "试探", { relationship: { favor: -1, taiziFavor: -6, revealRisk: 14 }, persona: { scheming_naive: 1 } }),
        ],
      },
      {
        id: "N1-soft",
        kind: "turn",
        turn: 2,
        stageLabel: "支线 · 顺毛稳场",
        directorNote: "顺毛成功但代价是更深依赖。",
        summary: "太子短暂放松警惕，你得到一次缓冲。",
        scene: "太子盯了你许久，最终把香囊推回你掌心。你听见自己心跳回落，却知道这只是暂时。东宫这条线稳了一点，别处却可能已经起火。",
        choiceCount: 2,
        choices: [
          createChoice("N1-soft", 1, "N2", "我顺势求他暗中护我一次，承诺今夜之后不再隐瞒。", "trust", "真诚", { relationship: { taiziFavor: 12, revealRisk: -6 } }),
          createChoice("N1-soft", 2, "N2", "我借机套他口风，想知道是谁先把消息递进东宫的。", "strategy", "克制", { relationship: { taiziFavor: 4, revealRisk: 3 }, persona: { scheming_naive: 1 } }),
        ],
      },
      {
        id: "N1-flirt",
        kind: "turn",
        turn: 2,
        stageLabel: "支线 · 反撩翻盘",
        directorNote: "暧昧升温，但危险同步上升。",
        summary: "你把审讯变成暧昧拉扯，风险也更高。",
        scene: "太子被你一句话逼得眯起眼，像想笑又像想罚。你看见他耳侧脉搏跳了一下，知道自己赌对了半步，却也把底线往前推得更危险。",
        choiceCount: 2,
        choices: [
          createChoice("N1-flirt", 1, "N2", "我继续贴近，借亲密逼他先亮底牌。", "tease", "暧昧", { relationship: { taiziFavor: 9, revealRisk: 10 } }),
          createChoice("N1-flirt", 2, "N2", "我忽然收住笑意，反问他到底想听真话还是想定我的罪。", "confrontation", "强势", { relationship: { taiziFavor: -4, revealRisk: 6 }, persona: { extrovert_introvert: 1 } }),
        ],
      },
      {
        id: "N2",
        kind: "turn",
        turn: 3,
        stageLabel: "Chapter 2 · 楚相来袭",
        directorNote: "楚白闯入，双线好感开始拉扯。",
        summary: "引入隐藏变量：太子好感、楚相好感。",
        scene: "殿门忽然被人推开，楚白披着夜色进来，视线先落在你，再落在太子。空气像绷紧的弦，任何一个称呼都可能刺穿谎言。",
        choiceCount: 3,
        choices: [
          createChoice("N2", 1, "N3", "我下意识躲到太子身后，把选择权交给他。", "observation", "克制", { relationship: { taiziFavor: 10, chuxiangFavor: -8, revealRisk: -2 } }),
          createChoice("N2", 2, "N3", "我当场拉太子下水，逼他和我站在同一条船上。", "tease", "挑衅", { relationship: { taiziFavor: 6, chuxiangFavor: 6, revealRisk: 8 }, persona: { extrovert_introvert: 1 } }),
          createChoice("N2", 3, "N3", "我把矛头引到自己身上，主动承认所有疑点由我承担。", "sacrifice", "决绝", { relationship: { taiziFavor: 4, chuxiangFavor: 10, revealRisk: 15 } }),
        ],
      },
      {
        id: "N3",
        kind: "turn",
        turn: 4,
        stageLabel: "Chapter 3 · 裴寂入局",
        directorNote: "大理寺介入，掉马风险上升。",
        summary: "关键变量：掉马风险值。",
        scene: "裴寂踏进东宫时，所有人都静了一瞬。他目光像刀，从你的喉结、袖口、步态一寸寸扫过去，像在拆一层随时会崩掉的伪装。",
        choiceCount: 3,
        choices: [
          createChoice("N3", 1, "N4", "我继续装太监，故意把嗓音压得更低。", "strategy", "克制", { relationship: { revealRisk: 18, peijiFavor: 4, peijiControl: 8 }, persona: { scheming_naive: 1 } }),
          createChoice("N3", 2, "N4", "我趁乱跑路，逼所有人转入追逐与战斗线。", "risk", "冒险", { relationship: { revealRisk: 12, generalFavor: 14 }, persona: { extrovert_introvert: 1 } }),
          createChoice("N3", 3, "N4", "我躲进密室只见太子，试图用旧情暂时封口。", "trust", "压抑", { relationship: { taiziFavor: 10, revealRisk: -3, peijiControl: 4 } }),
        ],
      },
      {
        id: "N4",
        kind: "turn",
        turn: 5,
        stageLabel: "Chapter 4 · 马车掉马",
        directorNote: "核心爆点：是否掉马、裴寂控制权。",
        summary: "全局关键节点，关系结构从此重排。",
        scene: "马车一颠，你束发的簪子被震落。裴寂抬手按住你肩膀，指尖停在你喉侧，眼神像在宣判。那一刻你知道，伪装已经不是秘密，而是筹码。",
        choiceCount: 3,
        choices: [
          createChoice("N4", 1, "N5", "我眼圈发红示弱，赌他会把我收进可控范围。", "soft", "脆弱", { relationship: { peijiFavor: 10, peijiControl: 22, revealRisk: 8 } }),
          createChoice("N4", 2, "N5", "我反手撩拨他，说既然都看穿了不如做同谋。", "tease", "危险", { relationship: { peijiFavor: 18, peijiControl: 12, darkness: 12, revealRisk: 16 } }),
          createChoice("N4", 3, "N5", "我半真半假讲一套权谋版本，试图把他拉进更大的局。", "strategy", "冷静", { relationship: { peijiFavor: 8, peijiControl: 6, revealRisk: 10 }, persona: { scheming_naive: 2 } }),
        ],
      },
      {
        id: "N5",
        kind: "turn",
        turn: 6,
        stageLabel: "Chapter 5 · 三男对峙",
        directorNote: "太子 + 将军 + 裴寂同场，选择决定主线归宿。",
        summary: "互动小说卖点节点，含隐藏 D 入口。",
        scene: "大理寺灯火通明，三道目光像三把不同形状的刀。太子要你回宫，将军要你离城，裴寂却只问你一句：你到底想活成谁的棋子。",
        choiceCount: 4,
        choices: [
          createChoice("N5", 1, "E-palace", "我站到太子身边，选宫廷线，把局势压回皇权框架。", "trust", "克制", { relationship: { taiziFavor: 16, powerBias: 12 } }),
          createChoice("N5", 2, "E-escape", "我抓住将军的手要他带我离开，选逃离线。", "risk", "决绝", { relationship: { generalFavor: 18, revealRisk: -8 } }),
          createChoice("N5", 3, "E-dark", "我看向裴寂，说愿意和他一起把规则撕开，走黑暗线。", "manipulation", "黑化", { relationship: { peijiFavor: 20, darkness: 20, peijiControl: 10 } }),
          createChoice("N5", 4, "N6", "我忽然以自伤逼停三人，触发隐藏 NP 入口。", "sacrifice", "失控", { relationship: { taiziFavor: 14, peijiFavor: 14, generalFavor: 14, revealRisk: 10 } }),
        ],
      },
      {
        id: "N6",
        kind: "turn",
        turn: 7,
        stageLabel: "Chapter 6 · 权力平衡线",
        directorNote: "NP 线：不再二选一，而是关系平衡。",
        summary: "触发条件建议：太子/裴寂/将军好感都 > 70。",
        scene: "你没有再选任何一个人，而是让三方都看见彼此的底牌。东宫的权力、将军的退路、裴寂的掌控欲在同一张桌上博弈，你第一次成为规则的制定者。",
        choiceCount: 4,
        choices: [
          createChoice("N6", 1, "E-palace", "偏太子：权力上升，但危险同步拉高。", "confrontation", "权谋", { relationship: { taiziFavor: 14, powerBias: 20, revealRisk: 10 } }),
          createChoice("N6", 2, "E-escape", "偏将军：安全感上升，但控制力下降。", "support", "温和", { relationship: { generalFavor: 14, powerBias: -12, revealRisk: -6 } }),
          createChoice("N6", 3, "E-dark", "偏裴寂：黑化值上升，关系更危险也更亲密。", "manipulation", "危险", { relationship: { peijiFavor: 14, darkness: 22, peijiControl: 16 } }),
          createChoice("N6", 4, "E-np", "端水平衡：维持三方微妙稳定，锁定 NP 结局。", "strategy", "冷静", { relationship: { taiziFavor: 8, peijiFavor: 8, generalFavor: 8, powerBias: 0, revealRisk: 2 } }),
        ],
      },
      createEndingNode("E-palace", "宫廷线结局", "你和太子把权力与情感绑在同一根绳上，东宫不再是牢笼，而是你亲手重写规则的棋盘。", "good"),
      createEndingNode("E-escape", "逃离线结局", "城门在身后合上，你终于拥有了没有宫墙的呼吸。只是某些名字，仍会在夜里轻轻叩门。", "open"),
      createEndingNode("E-dark", "黑暗线结局", "你与裴寂在彼此试探里沉沦，爱意和控制再也分不清边界。", "bittersweet"),
      createEndingNode("E-np", "NP 平衡线结局", "你没有成为任何人的附庸，而是让三方在你设定的平衡里共存，危险且稳定。", "bittersweet"),
    ],
  };
  return pkg;
}

async function withRequestTimeout(requestFactory, timeoutMs = 30000, timeoutMessage = "请求超时，请稍后重试") {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    return await requestFactory({ signal: controller.signal });
  } catch (err) {
    if (timedOut && err?.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

const nodeRows = computed(() => {
  const nodes = Array.isArray(storyPackage.value?.nodes) ? storyPackage.value.nodes : [];
  return nodes.slice().sort((a, b) => {
    const turnGap = Number(a?.turn || 0) - Number(b?.turn || 0);
    if (turnGap !== 0) {
      return turnGap;
    }
    return String(a?.id || "").localeCompare(String(b?.id || ""));
  });
});

const nodeIdOptions = computed(() => nodeRows.value.map((item) => item.id).filter(Boolean));
const selectedNode = computed(() => nodeRows.value.find((item) => item.id === selectedNodeId.value) || null);
const packagePreview = computed(() => JSON.stringify(buildPackagePayload(), null, 2));

const visualFlow = computed(() => {
  const nodes = nodeRows.value;
  if (!nodes.length) {
    return { width: 760, height: 280, nodes: [], edges: [], columns: [] };
  }

  const groups = new Map();
  for (const node of nodes) {
    const turn = Number(node?.turn || 1);
    if (!groups.has(turn)) {
      groups.set(turn, []);
    }
    groups.get(turn).push(node);
  }

  const turns = Array.from(groups.keys()).sort((a, b) => a - b);
  const orderedGroups = turns.map((turn) => {
    const rows = (groups.get(turn) || []).slice().sort((left, right) => {
      if (left.kind !== right.kind) {
        return left.kind === "turn" ? -1 : 1;
      }
      return String(left.id || "").localeCompare(String(right.id || ""));
    });
    return { turn, rows };
  });

  const cardWidth = desktopLayout.value ? 208 : 168;
  const cardHeight = desktopLayout.value ? 104 : 90;
  const xGap = desktopLayout.value ? 286 : 232;
  const yGap = desktopLayout.value ? 118 : 128;
  const paddingX = desktopLayout.value ? 42 : 34;
  const paddingY = desktopLayout.value ? 30 : 36;
  const maxRows = Math.max(...orderedGroups.map((item) => item.rows.length));
  const columns = orderedGroups.map((group, col) => ({
    turn: group.turn,
    title: chapterTitleByTurn(group.turn),
    x: paddingX + col * xGap,
    width: cardWidth,
  }));

  const layoutNodes = [];
  for (let col = 0; col < orderedGroups.length; col += 1) {
    const group = orderedGroups[col];
    const startY = paddingY + ((maxRows - group.rows.length) * yGap) / 2;
    for (let row = 0; row < group.rows.length; row += 1) {
      const node = group.rows[row];
      const fallbackX = paddingX + col * xGap;
      const fallbackY = startY + row * yGap;
      const override = nodePositionOverrides.value?.[node.id];
      layoutNodes.push({
        id: node.id,
        node,
        x: Number.isFinite(Number(override?.x)) ? Math.max(20, Number(override.x)) : fallbackX,
        y: Number.isFinite(Number(override?.y)) ? Math.max(46, Number(override.y)) : fallbackY,
        width: cardWidth,
        height: cardHeight,
      });
    }
  }

  const nodesWithPorts = layoutNodes.map((item) => {
    const inputHandle = getNodeInputPoint(item);
    const outputHandles = [];
    if (item.node.kind === "turn") {
      const choices = Array.isArray(item.node.choices) ? item.node.choices : [];
      for (let choiceIndex = 0; choiceIndex < choices.length; choiceIndex += 1) {
        const point = getChoiceOutputPoint(item, choiceIndex, choices.length);
        outputHandles.push({
          index: choiceIndex,
          label: CHOICE_LABELS[choiceIndex] || String(choiceIndex + 1),
          x: point.x,
          y: point.y,
          choice: choices[choiceIndex],
        });
      }
    }
    return {
      ...item,
      inputHandle,
      outputHandles,
    };
  });

  const byId = Object.fromEntries(nodesWithPorts.map((item) => [item.id, item]));
  const edges = [];
  for (const item of nodesWithPorts) {
    if (item.node.kind !== "turn") {
      continue;
    }
    const choices = Array.isArray(item.node.choices) ? item.node.choices : [];
    for (let index = 0; index < choices.length; index += 1) {
      const choice = choices[index];
      const target = byId[choice?.nextNodeId];
      if (!target) {
        continue;
      }
      const from = getChoiceOutputPoint(item, index, choices.length);
      const to = getNodeInputPoint(target);
      const curve = createBezierPath(from, to);
      edges.push({
        id: `${item.id}-${choice?.id || index}-${choice?.nextNodeId}`,
        from,
        to,
        path: curve.path,
        midX: curve.mid.x,
        midY: curve.mid.y,
        label: CHOICE_LABELS[index] || String(index + 1),
        sourceId: item.id,
        targetId: target.id,
        choiceIndex: index,
      });
    }
  }

  let maxRight = paddingX * 2 + (orderedGroups.length - 1) * xGap + cardWidth + 24;
  let maxBottom = paddingY * 2 + (maxRows - 1) * yGap + cardHeight + 24;
  for (const item of nodesWithPorts) {
    maxRight = Math.max(maxRight, item.x + item.width + 80);
    maxBottom = Math.max(maxBottom, item.y + item.height + 60);
  }

  return {
    width: Math.max(desktopLayout.value ? 1160 : 780, maxRight),
    height: Math.max(320, maxBottom),
    columns,
    nodes: nodesWithPorts,
    edges,
  };
});

const activeConnectionLine = computed(() => {
  const state = connectionState.value;
  if (!state?.startPoint || !state?.endPoint) {
    return null;
  }
  const curve = createBezierPath(state.startPoint, state.endPoint);
  return {
    path: curve.path,
    from: state.startPoint,
    to: state.endPoint,
  };
});

const graphSummary = computed(() => {
  const turnNodes = nodeRows.value.filter((item) => item.kind === "turn").length;
  const endingNodes = nodeRows.value.filter((item) => item.kind === "ending").length;
  const edgeCount = nodeRows.value.reduce((total, item) => total + (Array.isArray(item?.choices) ? item.choices.length : 0), 0);
  return { turnNodes, endingNodes, edgeCount };
});

const nodesByTurn = computed(() => {
  const grouped = new Map();
  for (const node of nodeRows.value) {
    const turn = Number(node?.turn || 1);
    if (!grouped.has(turn)) {
      grouped.set(turn, []);
    }
    grouped.get(turn).push(node);
  }
  return Array.from(grouped.entries())
    .sort((left, right) => left[0] - right[0])
    .map(([turn, nodes]) => ({
      turn,
      nodes,
    }));
});

const selectedOutgoingLinks = computed(() => {
  if (!selectedNode.value || selectedNode.value.kind !== "turn") {
    return [];
  }
  const idMap = Object.fromEntries(nodeRows.value.map((item) => [item.id, item]));
  return (selectedNode.value.choices || []).map((choice, index) => ({
    index,
    choice,
    target: idMap[choice.nextNodeId] || null,
  }));
});

const storyStatePreview = computed(() => {
  const relationship = buildPackagePayload()?.initialState?.relationship || {};
  return {
    taiziFavor: Number(relationship.taiziFavor || 0),
    chuxiangFavor: Number(relationship.chuxiangFavor || 0),
    peijiFavor: Number(relationship.peijiFavor || 0),
    generalFavor: Number(relationship.generalFavor || 0),
    revealRisk: Number(relationship.revealRisk || 0),
    peijiControl: Number(relationship.peijiControl || 0),
  };
});

function findLayoutNode(nodeId) {
  return visualFlow.value.nodes.find((item) => item.id === nodeId) || null;
}

function getBoardPointFromClient(clientX, clientY) {
  const board = canvasBoardRef.value;
  if (!board) {
    return null;
  }
  const rect = board.getBoundingClientRect();
  return {
    x: clientX - rect.left,
    y: clientY - rect.top,
  };
}

function updateNodePositionOverride(nodeId, x, y) {
  nodePositionOverrides.value = {
    ...(nodePositionOverrides.value || {}),
    [nodeId]: {
      x: Math.max(20, Math.round(x)),
      y: Math.max(46, Math.round(y)),
    },
  };
}

function releaseCanvasPointerEvents() {
  window.removeEventListener("pointermove", handleGlobalPointerMove);
  window.removeEventListener("pointerup", handleGlobalPointerUp);
  window.removeEventListener("pointercancel", handleGlobalPointerUp);
}

function attachCanvasPointerEvents() {
  window.addEventListener("pointermove", handleGlobalPointerMove);
  window.addEventListener("pointerup", handleGlobalPointerUp);
  window.addEventListener("pointercancel", handleGlobalPointerUp);
}

function findNodeByPoint(point, ignoreNodeId = "") {
  if (!point) {
    return null;
  }
  const capturePadding = 12;
  const nodes = visualFlow.value.nodes.slice().reverse();
  for (const item of nodes) {
    if (item.id === ignoreNodeId) {
      continue;
    }
    const withinX = point.x >= item.x - capturePadding && point.x <= item.x + item.width + capturePadding;
    const withinY = point.y >= item.y - capturePadding && point.y <= item.y + item.height + capturePadding;
    if (withinX && withinY) {
      return item;
    }
  }
  return null;
}

function applyConnection(sourceNodeId, choiceIndex, targetNodeId) {
  const source = nodeRows.value.find((node) => node.id === sourceNodeId);
  if (!source || source.kind !== "turn") {
    return;
  }
  ensureTurnChoices(source);
  if (!Array.isArray(source.choices) || !source.choices[choiceIndex]) {
    return;
  }
  source.choices[choiceIndex].nextNodeId = targetNodeId;
  selectedNodeId.value = sourceNodeId;
  error.value = "";
  success.value = `已连接：${sourceNodeId}.${formatChoiceLabel(choiceIndex)} → ${targetNodeId}`;
}

function handleGlobalPointerMove(event) {
  if (dragState.value) {
    const point = getBoardPointFromClient(event.clientX, event.clientY);
    if (!point) {
      return;
    }
    const nextX = dragState.value.originNodeX + (point.x - dragState.value.originPointerX);
    const nextY = dragState.value.originNodeY + (point.y - dragState.value.originPointerY);
    if (!dragState.value.moved && (Math.abs(nextX - dragState.value.originNodeX) > 2 || Math.abs(nextY - dragState.value.originNodeY) > 2)) {
      dragState.value.moved = true;
    }
    updateNodePositionOverride(dragState.value.nodeId, nextX, nextY);
    return;
  }
  if (connectionState.value) {
    const point = getBoardPointFromClient(event.clientX, event.clientY);
    if (!point) {
      return;
    }
    const target = findNodeByPoint(point, connectionState.value.sourceNodeId);
    connectionState.value = {
      ...connectionState.value,
      endPoint: point,
      hoverTargetId: target?.id || "",
    };
  }
}

function handleGlobalPointerUp(event) {
  if (dragState.value) {
    const current = dragState.value;
    dragState.value = null;
    if (current.moved) {
      blockNodeClickUntil.value = Date.now() + 240;
      persistNodePositionOverrides();
    }
    if (!connectionState.value) {
      releaseCanvasPointerEvents();
    }
    return;
  }
  if (connectionState.value) {
    const point = getBoardPointFromClient(event.clientX, event.clientY);
    const target = findNodeByPoint(point, connectionState.value.sourceNodeId);
    if (target?.id) {
      applyConnection(connectionState.value.sourceNodeId, connectionState.value.choiceIndex, target.id);
    }
    connectionState.value = null;
    if (!dragState.value) {
      releaseCanvasPointerEvents();
    }
  }
}

function beginNodeDrag(nodeId, event) {
  if (event.button !== 0 || connectionState.value) {
    return;
  }
  const layoutNode = findLayoutNode(nodeId);
  if (!layoutNode) {
    return;
  }
  const point = getBoardPointFromClient(event.clientX, event.clientY);
  if (!point) {
    return;
  }
  dragState.value = {
    nodeId,
    originPointerX: point.x,
    originPointerY: point.y,
    originNodeX: layoutNode.x,
    originNodeY: layoutNode.y,
    moved: false,
  };
  attachCanvasPointerEvents();
}

function beginConnectionDrag(nodeId, choiceIndex, event) {
  if (event.button !== 0) {
    return;
  }
  const layoutNode = findLayoutNode(nodeId);
  if (!layoutNode) {
    return;
  }
  const sourceChoices = Array.isArray(layoutNode.node?.choices) ? layoutNode.node.choices.length : 0;
  if (choiceIndex < 0 || choiceIndex >= sourceChoices) {
    return;
  }
  const point = getBoardPointFromClient(event.clientX, event.clientY);
  if (!point) {
    return;
  }
  const startPoint = getChoiceOutputPoint(layoutNode, choiceIndex, sourceChoices);
  connectionState.value = {
    sourceNodeId: nodeId,
    choiceIndex,
    startPoint,
    endPoint: point,
    hoverTargetId: "",
  };
  attachCanvasPointerEvents();
}

function onNodeCardClick(nodeId) {
  if (Date.now() < blockNodeClickUntil.value) {
    return;
  }
  selectedNodeId.value = nodeId;
}

function ensureTurnChoices(node) {
  if (!node || node.kind !== "turn") {
    if (node) {
      node.choiceCount = 0;
      node.choices = [];
    }
    return;
  }
  const desiredCount = clampChoiceCount(node.choiceCount, Array.isArray(node.choices) ? node.choices.length || 3 : 3);
  node.choiceCount = desiredCount;

  if (!Array.isArray(node.choices)) {
    node.choices = [];
  }
  while (node.choices.length < desiredCount) {
    node.choices.push(createChoice(node.id || "N", node.choices.length + 1, defaultNextNodeId(node.id)));
  }
  if (node.choices.length > desiredCount) {
    node.choices = node.choices.slice(0, desiredCount);
  }

  node.choices = node.choices.map((item, index) => {
    const normalized = typeof item === "object" && item ? item : {};
    const style = safeText(normalized.style) || "dialogue";
    const tone = safeText(normalized.tone) || "生活化";
    const fallback = createChoice(node.id, index + 1, defaultNextNodeId(node.id), "", style, tone);
    return {
      ...fallback,
      ...normalized,
      id: safeText(normalized.id) || `${node.id}-C${index + 1}`,
      text: String(normalized.text || ""),
      nextNodeId: safeText(normalized.nextNodeId) || defaultNextNodeId(node.id),
      style,
      tone,
      effects: {
        persona: {
          ...(normalized?.effects?.persona || {}),
        },
        relationship: {
          ...(normalized?.effects?.relationship || {}),
        },
      },
    };
  });
}

function defaultNextNodeId(excludeId = "") {
  const endings = nodeRows.value.filter((item) => item.kind === "ending" && item.id !== excludeId);
  if (endings.length) {
    return endings[0].id;
  }
  const turns = nodeRows.value.filter((item) => item.id && item.id !== excludeId);
  if (turns.length) {
    return turns[0].id;
  }
  return excludeId || "N1";
}

function normalizePackageShape() {
  const sourceNodes = Array.isArray(storyPackage.value?.nodes) ? storyPackage.value.nodes : [];
  const usedIds = new Set();
  const normalized = [];

  for (let index = 0; index < sourceNodes.length; index += 1) {
    const raw = sourceNodes[index];
    if (!raw || typeof raw !== "object") {
      continue;
    }

    let id = safeText(raw.id) || `N${index + 1}`;
    if (usedIds.has(id)) {
      let suffix = 2;
      while (usedIds.has(`${id}-${suffix}`)) {
        suffix += 1;
      }
      id = `${id}-${suffix}`;
    }
    usedIds.add(id);

    const kind = safeText(raw.kind).toLowerCase() === "ending" ? "ending" : "turn";
    const turn = Number.isFinite(Number(raw.turn)) ? Math.max(1, Math.floor(Number(raw.turn))) : index + 1;
    const node = {
      id,
      kind,
      turn,
      stageLabel: String(raw.stageLabel || (kind === "ending" ? "结局" : "剧情推进")),
      directorNote: String(raw.directorNote || ""),
      summary: String(raw.summary || ""),
      scene: String(raw.scene || ""),
      endingType: safeText(raw.endingType),
      choiceCount: kind === "turn" ? clampChoiceCount(raw.choiceCount, Array.isArray(raw.choices) ? raw.choices.length || 3 : 3) : 0,
      choices: Array.isArray(raw.choices) ? raw.choices : [],
    };
    ensureTurnChoices(node);
    normalized.push(node);
  }

  if (!normalized.length) {
    storyPackage.value = createStarterPackage();
    selectedNodeId.value = "N1";
    return;
  }

  storyPackage.value.nodes = normalized;
  clearDanglingNodePositionOverrides(usedIds);
  const rootNodeId = safeText(storyPackage.value.rootNodeId);
  storyPackage.value.rootNodeId = usedIds.has(rootNodeId) ? rootNodeId : normalized[0].id;

  if (!storyPackage.value.initialState || typeof storyPackage.value.initialState !== "object") {
    storyPackage.value.initialState = buildDefaultInitialState();
  }

  if (!usedIds.has(selectedNodeId.value)) {
    selectedNodeId.value = storyPackage.value.rootNodeId;
  }
}

function buildPackagePayload() {
  const payload = deepClone(storyPackage.value || {});
  const title = safeText(form.value.title) || safeText(payload.title) || "未命名互动宇宙";
  const opening = safeText(form.value.opening) || safeText(payload.opening) || title;
  const role = safeText(form.value.role) || safeText(payload.role) || "主人公";
  payload.title = title;
  payload.opening = opening;
  payload.role = role;
  payload.version = Number(payload.version || 2);
  payload.generatedBy = safeText(payload.generatedBy) || "library_workbench_studio_v1";

  const initialState = payload.initialState && typeof payload.initialState === "object"
    ? payload.initialState
    : buildDefaultInitialState();
  payload.initialState = {
    ...buildDefaultInitialState(),
    ...initialState,
    relationship: {
      ...buildDefaultInitialState().relationship,
      ...(initialState.relationship || {}),
    },
    persona: {
      ...buildDefaultInitialState().persona,
      ...(initialState.persona || {}),
    },
    flags: Array.isArray(initialState.flags) ? initialState.flags : [],
  };

  payload.nodes = (Array.isArray(payload.nodes) ? payload.nodes : []).map((raw, index) => {
    const kind = safeText(raw.kind).toLowerCase() === "ending" ? "ending" : "turn";
    const node = {
      id: safeText(raw.id) || `N${index + 1}`,
      kind,
      turn: Number.isFinite(Number(raw.turn)) ? Math.max(1, Math.floor(Number(raw.turn))) : index + 1,
      stageLabel: safeText(raw.stageLabel) || (kind === "ending" ? "结局" : "剧情推进"),
      directorNote: String(raw.directorNote || ""),
      summary: String(raw.summary || ""),
      scene: String(raw.scene || ""),
      endingType: safeText(raw.endingType),
      choiceCount: kind === "turn" ? clampChoiceCount(raw.choiceCount, Array.isArray(raw.choices) ? raw.choices.length || 3 : 3) : 0,
      choices: [],
    };

    if (kind === "turn") {
      const desiredCount = node.choiceCount;
      const choices = Array.isArray(raw.choices) ? raw.choices.slice(0, desiredCount) : [];
      while (choices.length < desiredCount) {
        choices.push(createChoice(node.id, choices.length + 1, defaultNextNodeId(node.id)));
      }
      node.choices = choices.map((choice, cIndex) => {
        const normalized = typeof choice === "object" && choice ? choice : {};
        const style = safeText(normalized.style) || "dialogue";
        return {
          id: safeText(normalized.id) || `${node.id}-C${cIndex + 1}`,
          text: String(normalized.text || ""),
          nextNodeId: safeText(normalized.nextNodeId) || defaultNextNodeId(node.id),
          style,
          tone: safeText(normalized.tone) || "生活化",
          effects: {
            persona: {
              ...(normalized?.effects?.persona || {}),
            },
            relationship: {
              ...(normalized?.effects?.relationship || {}),
            },
          },
        };
      });
    }
    return node;
  });

  const nodeIds = new Set(payload.nodes.map((item) => item.id));
  if (!nodeIds.has(payload.rootNodeId)) {
    payload.rootNodeId = payload.nodes[0]?.id || "N1";
  }

  return payload;
}

function ensureFormDefaultMeta() {
  if (!safeText(form.value.title)) {
    form.value.title = safeText(storyPackage.value.title) || "未命名互动宇宙";
  }
  if (!safeText(form.value.opening)) {
    form.value.opening = safeText(storyPackage.value.opening) || "请在这里输入你的故事开头";
  }
  if (!safeText(form.value.summary)) {
    form.value.summary = safeText(storyPackage.value.opening).slice(0, 80);
  }
}

function setChoiceCount(node, rawCount) {
  if (!node || node.kind !== "turn") {
    return;
  }
  node.choiceCount = clampChoiceCount(rawCount, node.choiceCount || 3);
  ensureTurnChoices(node);
}

function addTurnNode() {
  normalizePackageShape();
  const existingIds = new Set(nodeRows.value.map((item) => item.id));
  let idx = nodeRows.value.filter((item) => item.kind === "turn").length + 1;
  let id = `N${idx}`;
  while (existingIds.has(id)) {
    idx += 1;
    id = `N${idx}`;
  }
  const maxTurn = nodeRows.value.reduce((acc, item) => Math.max(acc, Number(item?.turn || 0)), 0);
  storyPackage.value.nodes.push({
    id,
    kind: "turn",
    turn: maxTurn + 1,
    stageLabel: `第${maxTurn + 1}幕`,
    directorNote: "",
    summary: "",
    scene: "",
    choiceCount: 3,
    choices: [
      createChoice(id, 1, defaultNextNodeId(id)),
      createChoice(id, 2, defaultNextNodeId(id)),
      createChoice(id, 3, defaultNextNodeId(id)),
    ],
  });
  selectedNodeId.value = id;
  normalizePackageShape();
}

function addEndingNode() {
  normalizePackageShape();
  const existingIds = new Set(nodeRows.value.map((item) => item.id));
  let idx = nodeRows.value.filter((item) => item.kind === "ending").length + 1;
  let id = `E-${idx}`;
  while (existingIds.has(id)) {
    idx += 1;
    id = `E-${idx}`;
  }
  const maxTurn = nodeRows.value.reduce((acc, item) => Math.max(acc, Number(item?.turn || 0)), 0);
  storyPackage.value.nodes.push({
    id,
    kind: "ending",
    turn: maxTurn + 1,
    stageLabel: "结局",
    directorNote: "",
    summary: "",
    scene: "",
    endingType: "open",
    choiceCount: 0,
    choices: [],
  });
  selectedNodeId.value = id;
  normalizePackageShape();
}

function removeNode(nodeId) {
  normalizePackageShape();
  if (storyPackage.value.nodes.length <= 1) {
    error.value = "至少保留一个节点。";
    return;
  }

  storyPackage.value.nodes = storyPackage.value.nodes.filter((item) => item.id !== nodeId);
  if (!storyPackage.value.nodes.length) {
    storyPackage.value = createStarterPackage();
    selectedNodeId.value = "N1";
    return;
  }

  const aliveNodeIds = new Set(storyPackage.value.nodes.map((item) => item.id));
  if (!aliveNodeIds.has(storyPackage.value.rootNodeId)) {
    storyPackage.value.rootNodeId = storyPackage.value.nodes[0].id;
  }

  for (const node of storyPackage.value.nodes) {
    if (node.kind !== "turn") {
      node.choiceCount = 0;
      node.choices = [];
      continue;
    }
    ensureTurnChoices(node);
    node.choices = node.choices.map((choice) => {
      const nextNodeId = aliveNodeIds.has(choice.nextNodeId) ? choice.nextNodeId : defaultNextNodeId(node.id);
      return {
        ...choice,
        nextNodeId,
      };
    });
  }

  if (!aliveNodeIds.has(selectedNodeId.value)) {
    selectedNodeId.value = storyPackage.value.rootNodeId;
  }
  success.value = `已删除节点 ${nodeId}`;
}

function applyNodeKind(node, nextKind) {
  if (!node) {
    return;
  }
  node.kind = nextKind === "ending" ? "ending" : "turn";
  if (node.kind === "turn") {
    node.choiceCount = clampChoiceCount(node.choiceCount || 3, 3);
    ensureTurnChoices(node);
  } else {
    node.choiceCount = 0;
    node.choices = [];
  }
}

function setAsRoot(nodeId) {
  if (!nodeId) {
    return;
  }
  storyPackage.value.rootNodeId = nodeId;
  success.value = `已将 ${nodeId} 设为根节点`;
}

function formatNodeTag(node) {
  return node.kind === "ending" ? "END" : `T${node.turn}`;
}

function formatChoiceLabel(index) {
  return CHOICE_LABELS[index] || `C${index + 1}`;
}

function chapterTitleByTurn(turn) {
  const first = nodeRows.value.find((node) => Number(node?.turn || 0) === Number(turn));
  if (!first) {
    return `Chapter ${turn}`;
  }
  const label = safeText(first.stageLabel);
  return label || `Chapter ${turn}`;
}

function shortSummary(text) {
  const value = safeText(text);
  return value.length > 24 ? `${value.slice(0, 24)}…` : value;
}

function applyImperialOutlineTemplate() {
  storyPackage.value = createImperialOutlinePackage();
  form.value.title = storyPackage.value.title;
  form.value.opening = storyPackage.value.opening;
  form.value.summary = "东宫修罗场主线 + 隐藏 NP 权力平衡线";
  form.value.role = storyPackage.value.role;
  selectedNodeId.value = storyPackage.value.rootNodeId;
  success.value = "已套用东宫修罗场大纲模板";
  error.value = "";
  normalizePackageShape();
}

async function aiParseOutline() {
  const outline = safeText(form.value.outlineText);
  if (!outline) {
    error.value = "请先粘贴剧情大纲，再点击 AI 解析。";
    return;
  }
  error.value = "";
  success.value = "";
  parseWorking.value = true;
  try {
    const payload = {
      outline,
      title: safeText(form.value.title),
      opening: safeText(form.value.opening),
      role: safeText(form.value.role) || "主人公",
      provider: safeText(form.value.provider) || "volcengine",
      package: buildPackagePayload(),
    };
    const result = await withRequestTimeout(
      (requestOptions) => parseLibraryWorkbenchOutline(payload, requestOptions),
      65000,
      "AI 解析大纲超时（65s），请重试。"
    );
    if (result?.package && typeof result.package === "object") {
      storyPackage.value = result.package;
      form.value.title = safeText(result.package.title) || form.value.title;
      form.value.opening = safeText(result.package.opening) || form.value.opening;
      form.value.role = safeText(result.package.role) || form.value.role;
      normalizePackageShape();
      selectedNodeId.value = safeText(result.package.rootNodeId) || storyPackage.value.rootNodeId || "N1";
      const nodeStats = result?.generated || {};
      const turnCount = Number(nodeStats.turnNodes || 0);
      const endingCount = Number(nodeStats.endingNodes || 0);
      success.value = `AI 已解析大纲：${turnCount} 个剧情节点，${endingCount} 个结局节点。`;
    } else {
      throw new Error("AI 返回结果异常，请重试。");
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "AI 解析大纲失败";
  } finally {
    parseWorking.value = false;
  }
}

async function aiCompleteNode(mode) {
  normalizePackageShape();
  const node = selectedNode.value;
  if (!node) {
    error.value = "请先选择一个节点。";
    return;
  }
  if (mode !== "scene" && node.kind === "turn" && Number(node.choiceCount || node.choices?.length || 3) !== 3) {
    error.value = "当前节点不是 3 选项，AI 选项补写暂只支持 3 选项节点。可改为“AI 补写正文”或先把选项数改为 3。";
    return;
  }

  error.value = "";
  success.value = "";
  aiWorking.value = true;
  try {
    const payload = {
      package: buildPackagePayload(),
      nodeId: node.id,
      mode,
      opening: safeText(form.value.opening),
      title: safeText(form.value.title),
      role: safeText(form.value.role) || "主人公",
      provider: safeText(form.value.provider) || "volcengine",
    };
    const result = await withRequestTimeout(
      (requestOptions) => completeLibraryWorkbenchNode(payload, requestOptions),
      45000,
      "AI 补写超时（45s），请重试。"
    );
    if (result?.package && typeof result.package === "object") {
      storyPackage.value = result.package;
    }
    normalizePackageShape();
    selectedNodeId.value = result?.nodeId || node.id;
    const modeLabel = mode === "scene" ? "正文" : mode === "choices" ? "选项" : "正文+选项";
    success.value = `AI 已补写节点 ${selectedNodeId.value} 的${modeLabel}`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "AI 补写失败";
  } finally {
    aiWorking.value = false;
  }
}

async function refreshImportedRows() {
  loadingRows.value = true;
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  libraryRows.value = rows;
  loadingRows.value = false;
}

function upsertLibraryStoryCacheRow(row) {
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  const nextRows = [row, ...rows.filter((item) => item?.id !== row.id)];
  writeLibraryStoriesCache(nextRows);
}

function removeLibraryStoryCacheRow(storyId) {
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  writeLibraryStoriesCache(rows.filter((item) => item?.id !== storyId));
}

async function handlePublishToLibrary() {
  importing.value = true;
  error.value = "";
  success.value = "";
  try {
    const packagePayload = buildPackagePayload();
    const payload = {
      storyId: safeText(form.value.storyId) || undefined,
      title: safeText(form.value.title) || packagePayload.title,
      opening: safeText(form.value.opening) || packagePayload.opening,
      summary: safeText(form.value.summary) || safeText(form.value.opening).slice(0, 80),
      sortOrder: parseSortOrder(form.value.sortOrder),
      package: packagePayload,
    };
    const result = await importLibraryStoryPackage(payload);
    success.value = `发布成功：${result.title}（ID: ${result.storyId}）`;
    sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
    upsertLibraryStoryCacheRow({
      id: result.storyId,
      title: result.title,
      summary: result.summary,
      opening: result.opening,
      seedReady: true,
      seedGenerating: false,
      seedUpdatedAt: Math.floor(Date.now() / 1000),
      seedSessionId: result.seedSessionId || `seed-${result.storyId}`,
    });
    await refreshImportedRows();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "发布失败";
  } finally {
    importing.value = false;
  }
}

async function deleteByStoryId(storyId) {
  if (!storyId) {
    error.value = "请先填要删除的故事 ID。";
    return;
  }
  deleting.value = true;
  error.value = "";
  success.value = "";
  deleteReceipt.value = null;
  const startedAt = performance.now();
  try {
    const result = await withRequestTimeout(
      (requestOptions) => deleteImportedLibraryStory(storyId, requestOptions),
      12000,
      "删除请求超时（12s），请检查后端是否卡住。"
    );
    if (!result?.storyDeleted) {
      throw new Error("服务端未删除书市主记录，请重试。");
    }
    const elapsedMs = Math.round(performance.now() - startedAt);
    deleteReceipt.value = {
      storyId: result.storyId,
      storyDeleted: Boolean(result.storyDeleted),
      seedDeleted: Boolean(result.seedDeleted),
      elapsedMs,
      at: new Date().toLocaleString(),
    };
    success.value = `已删除：${result.storyId}（${elapsedMs}ms）`;
    sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
    removeLibraryStoryCacheRow(result.storyId);
    await refreshImportedRows();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deleting.value = false;
  }
}

async function handleDeleteImported() {
  const storyId = safeText(form.value.storyId);
  await deleteByStoryId(storyId);
}

function backToMarket() {
  sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
  router.push("/bookshelf?tab=public");
}

onMounted(() => {
  loadWorkbenchLayoutPreference();
  loadNodePositionOverrides();
  ensureFormDefaultMeta();
  normalizePackageShape();
  void refreshImportedRows();
});

onUnmounted(() => {
  releaseCanvasPointerEvents();
});
</script>

<template>
  <main :class="shellClass">
    <section :class="pageClass">
      <div :class="contentClass">
        <header class="flex items-start justify-between gap-3">
          <div class="space-y-2">
            <p class="text-xs uppercase tracking-[0.18em] text-paper-700/55">Hidden Workbench</p>
            <h1 class="font-serif text-3xl font-semibold text-paper-900">隐藏工作台 · 可视化剧情编排</h1>
            <p class="text-sm text-paper-700/72">先看全局分支图，再按节点编辑，最后发布到公共书城。</p>
          </div>
          <button
            class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-[0.72rem] font-semibold text-paper-800"
            @click="toggleWorkbenchLayout"
          >
            {{ desktopLayout ? "切回手机端" : "切换电脑端横屏" }}
          </button>
        </header>

        <section class="workflow-layout">
          <aside class="workflow-pane workflow-left space-y-4 rounded-2xl border border-paper-200 bg-white/88 p-4">
            <section class="space-y-3">
              <p class="text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-paper-700/65">Project</p>
              <div class="flex flex-wrap gap-2">
                <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800" @click="applyImperialOutlineTemplate">
                  套用：东宫修罗场大纲
                </button>
                <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800" @click="addTurnNode">+ Turn</button>
                <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800" @click="addEndingNode">+ Ending</button>
              </div>
              <input v-model="form.title" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="书城标题" />
              <textarea v-model="form.opening" class="min-h-[4rem] w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm leading-6" placeholder="故事开头（工作台主上下文）" />
              <div class="space-y-2 rounded-xl border border-paper-200 bg-paper-50 p-2">
                <p class="text-[0.68rem] font-semibold text-paper-700/70">AI 大纲解析</p>
                <textarea
                  v-model="form.outlineText"
                  class="min-h-[8.5rem] w-full rounded-lg border border-paper-200 bg-white px-2.5 py-2 text-xs leading-5"
                  placeholder="把你的剧情大纲粘贴在这里，点击“AI 解析大纲”自动生成工作流节点。"
                />
                <button
                  class="active-press rounded-lg border border-paper-300 bg-white px-3 py-1.5 text-xs font-semibold text-paper-800 disabled:opacity-55"
                  :disabled="parseWorking"
                  @click="aiParseOutline"
                >
                  {{ parseWorking ? "解析中..." : "AI 解析大纲" }}
                </button>
              </div>
            </section>

            <section class="space-y-2 rounded-xl border border-paper-200 bg-paper-50 p-3">
              <p class="text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-paper-700/65">State Variables</p>
              <div class="grid grid-cols-2 gap-2 text-[0.72rem] text-paper-800">
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">太子好感 {{ storyStatePreview.taiziFavor }}</p>
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">楚相好感 {{ storyStatePreview.chuxiangFavor }}</p>
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">裴寂好感 {{ storyStatePreview.peijiFavor }}</p>
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">将军好感 {{ storyStatePreview.generalFavor }}</p>
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">掉马风险 {{ storyStatePreview.revealRisk }}</p>
                <p class="rounded-lg border border-paper-200 bg-white px-2 py-1">裴寂控制 {{ storyStatePreview.peijiControl }}</p>
              </div>
            </section>

            <section class="space-y-2">
              <p class="text-[0.7rem] font-semibold uppercase tracking-[0.1em] text-paper-700/65">Node Tree</p>
              <div class="max-h-[42rem] space-y-2 overflow-y-auto rounded-xl border border-paper-200 bg-paper-50 p-2">
                <div v-for="group in nodesByTurn" :key="group.turn" class="space-y-1 rounded-lg border border-paper-200 bg-white p-2">
                  <p class="text-[0.68rem] font-semibold text-paper-700">Turn {{ group.turn }} · {{ chapterTitleByTurn(group.turn) }}</p>
                  <button
                    v-for="node in group.nodes"
                    :key="node.id"
                    class="active-press flex w-full items-center justify-between rounded-md border px-2 py-1.5 text-left text-xs"
                    :class="selectedNodeId === node.id ? 'border-paper-600 bg-paper-100 text-paper-900' : 'border-paper-200 bg-white text-paper-700'"
                    @click="selectedNodeId = node.id"
                  >
                    <span class="truncate pr-2">{{ node.id }} · {{ shortSummary(node.stageLabel || node.summary) }}</span>
                    <span class="rounded-md bg-paper-100 px-1.5 py-0.5 text-[0.62rem] font-semibold text-paper-700">{{ formatNodeTag(node) }}</span>
                  </button>
                </div>
              </div>
            </section>
          </aside>

          <section class="workflow-pane workflow-canvas rounded-2xl border border-paper-200 bg-white/88 p-4">
            <div class="flex items-center justify-between">
              <h2 class="font-serif text-lg font-semibold text-paper-900">Workflow Canvas</h2>
              <p class="text-[0.68rem] text-paper-700/70">Turn {{ graphSummary.turnNodes }} · Ending {{ graphSummary.endingNodes }} · 跳转 {{ graphSummary.edgeCount }}</p>
            </div>
            <p class="mt-1 text-[0.68rem] text-paper-700/70">拖拽节点可重排，按住右侧输出点并拖到目标节点可建立跳转。</p>
            <div class="mt-3 overflow-x-auto overflow-y-hidden rounded-xl border border-paper-200 bg-paper-50">
              <div ref="canvasBoardRef" class="relative select-none" :style="{ width: `${visualFlow.width}px`, height: `${visualFlow.height}px` }">
                <div
                  v-for="column in visualFlow.columns"
                  :key="`col-${column.turn}`"
                  class="absolute rounded-md bg-white/75 px-2 py-1 text-[0.64rem] font-semibold text-paper-700"
                  :style="{ left: `${column.x}px`, top: '6px', width: `${column.width}px` }"
                >
                  {{ chapterTitleByTurn(column.turn) }}
                </div>
                <svg class="absolute inset-0 h-full w-full" :viewBox="`0 0 ${visualFlow.width} ${visualFlow.height}`">
                  <defs>
                    <marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                      <path d="M0,0 L8,4 L0,8 z" fill="rgba(111,98,88,0.7)" />
                    </marker>
                  </defs>
                  <path
                    v-for="edge in visualFlow.edges"
                    :key="edge.id"
                    :d="edge.path"
                    fill="none"
                    stroke="rgba(111,98,88,0.5)"
                    stroke-width="1.8"
                    marker-end="url(#flow-arrow)"
                  />
                  <path
                    v-if="activeConnectionLine"
                    :d="activeConnectionLine.path"
                    fill="none"
                    stroke="rgba(217,119,6,0.95)"
                    stroke-width="2.2"
                    stroke-dasharray="4 4"
                    marker-end="url(#flow-arrow)"
                  />
                  <g v-for="edge in visualFlow.edges" :key="`${edge.id}-label`">
                    <rect :x="edge.midX - 7" :y="edge.midY - 8" width="14" height="14" rx="6" fill="rgba(255,255,255,0.9)" />
                    <text :x="edge.midX" :y="edge.midY + 3" font-size="9" text-anchor="middle" fill="rgba(74,59,50,0.85)">{{ edge.label }}</text>
                  </g>
                </svg>

                <div
                  v-for="item in visualFlow.nodes"
                  :key="item.id"
                  class="workflow-node absolute rounded-xl border px-2 py-2 text-left"
                  :class="[
                    selectedNodeId === item.id ? 'border-paper-700 bg-white text-paper-900 shadow-sm' : 'border-paper-300 bg-white/94 text-paper-800',
                    item.node.kind === 'ending' ? 'workflow-node-ending' : '',
                    connectionState?.hoverTargetId === item.id ? 'workflow-node-drop-target' : ''
                  ]"
                  :style="{ left: `${item.x}px`, top: `${item.y}px`, width: `${item.width}px`, minHeight: `${item.height}px` }"
                  @pointerdown="beginNodeDrag(item.id, $event)"
                  @click="onNodeCardClick(item.id)"
                >
                  <p class="flex items-center justify-between text-[0.68rem] font-semibold">
                    <span>{{ item.id }}</span>
                    <span class="rounded-md bg-paper-100 px-1.5 py-0.5">{{ item.node.kind === "ending" ? "END" : `T${item.node.turn}` }}</span>
                  </p>
                  <p class="mt-1 text-[0.7rem] leading-4 text-paper-700/88">{{ shortSummary(item.node.stageLabel || item.node.summary) }}</p>
                  <div v-if="item.node.kind === 'turn'" class="mt-1 flex gap-1 text-[0.62rem] text-paper-700/72">
                    <span
                      v-for="(choice, index) in item.node.choices"
                      :key="choice.id || `${item.id}-${index}`"
                      class="rounded border border-paper-200 bg-paper-50 px-1.5 py-0.5"
                    >
                      {{ formatChoiceLabel(index) }}
                    </span>
                  </div>
                </div>

                <div
                  v-for="item in visualFlow.nodes"
                  :key="`${item.id}-input`"
                  class="workflow-handle workflow-handle-input"
                  :class="connectionState?.hoverTargetId === item.id ? 'workflow-handle-input-hover' : ''"
                  :style="{ left: `${item.inputHandle.x}px`, top: `${item.inputHandle.y}px` }"
                />

                <template v-for="item in visualFlow.nodes.filter((nodeItem) => nodeItem.node.kind === 'turn')" :key="`${item.id}-outputs`">
                  <button
                    v-for="handle in item.outputHandles"
                    :key="`${item.id}-output-${handle.index}`"
                    class="workflow-handle workflow-handle-output"
                    :style="{ left: `${handle.x}px`, top: `${handle.y}px` }"
                    type="button"
                    :title="`从 ${item.id}.${handle.label} 拉线`"
                    @pointerdown.stop.prevent="beginConnectionDrag(item.id, handle.index, $event)"
                  >
                    {{ handle.label }}
                  </button>
                </template>
              </div>
            </div>
          </section>

          <aside class="workflow-pane workflow-inspector rounded-2xl border border-paper-200 bg-white/88 p-4">
            <div v-if="selectedNode" class="space-y-3">
              <div class="flex items-center justify-between">
                <h3 class="font-serif text-lg font-semibold text-paper-900">Node Inspector</h3>
                <div class="flex gap-2">
                  <button class="active-press rounded-lg border border-paper-300 bg-white px-2 py-1 text-xs font-semibold text-paper-700" @click="setAsRoot(selectedNode.id)">设为根节点</button>
                  <button class="active-press rounded-lg border border-red-300 bg-white px-2 py-1 text-xs font-semibold text-red-700" @click="removeNode(selectedNode.id)">删除</button>
                </div>
              </div>
              <p class="font-mono text-xs text-paper-700">当前节点：{{ selectedNode.id }}</p>
              <div class="grid gap-2 sm:grid-cols-4">
                <select :value="selectedNode.kind" class="rounded-xl border border-paper-200 bg-white px-2 py-2 text-xs" @change="applyNodeKind(selectedNode, $event.target.value)">
                  <option value="turn">turn</option>
                  <option value="ending">ending</option>
                </select>
                <input v-model.number="selectedNode.turn" type="number" min="1" class="rounded-xl border border-paper-200 bg-white px-2 py-2 text-xs" placeholder="turn" />
                <input v-model="selectedNode.stageLabel" class="rounded-xl border border-paper-200 bg-white px-2 py-2 text-xs" placeholder="阶段标题" />
                <select v-if="selectedNode.kind === 'turn'" :value="selectedNode.choiceCount" class="rounded-xl border border-paper-200 bg-white px-2 py-2 text-xs" @change="setChoiceCount(selectedNode, $event.target.value)">
                  <option value="2">2 选项</option>
                  <option value="3">3 选项</option>
                  <option value="4">4 选项</option>
                </select>
              </div>
              <input v-model="selectedNode.directorNote" class="w-full rounded-xl border border-paper-200 bg-white px-3 py-2 text-xs" placeholder="局势提示（directorNote）" />
              <textarea v-model="selectedNode.summary" class="min-h-[3.8rem] w-full rounded-xl border border-paper-200 bg-white px-3 py-2 text-xs leading-5" placeholder="节点摘要（summary）" />
              <textarea v-model="selectedNode.scene" class="min-h-[8.2rem] w-full rounded-xl border border-paper-200 bg-white px-3 py-2 text-xs leading-6" placeholder="节点正文（scene）" />

              <template v-if="selectedNode.kind === 'turn'">
                <div class="space-y-2 rounded-xl border border-paper-200 bg-paper-50 p-3">
                  <p class="text-xs font-semibold tracking-[0.08em] text-paper-700/70">选项与跳转</p>
                  <div v-for="link in selectedOutgoingLinks" :key="link.choice.id || `${selectedNode.id}-${link.index}`" class="space-y-2 rounded-lg border border-paper-200 bg-white px-2 py-2">
                    <p class="font-mono text-[0.68rem] text-paper-700">{{ formatChoiceLabel(link.index) }} → {{ link.target?.id || "未连接" }}</p>
                    <textarea v-model="link.choice.text" class="min-h-[3rem] w-full rounded-lg border border-paper-200 bg-paper-50 px-2 py-1.5 text-xs leading-5" placeholder="选项文案" />
                    <div class="grid gap-2 sm:grid-cols-3">
                      <select v-model="link.choice.nextNodeId" class="rounded-lg border border-paper-200 bg-paper-50 px-2 py-1.5 text-xs">
                        <option v-for="id in nodeIdOptions" :key="id" :value="id">{{ id }}</option>
                      </select>
                      <input v-model="link.choice.style" class="rounded-lg border border-paper-200 bg-paper-50 px-2 py-1.5 text-xs" placeholder="style" />
                      <input v-model="link.choice.tone" class="rounded-lg border border-paper-200 bg-paper-50 px-2 py-1.5 text-xs" placeholder="tone" />
                    </div>
                  </div>
                </div>
                <p v-if="selectedNode.choiceCount !== 3" class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[0.72rem] text-amber-800">
                  AI 选项补写当前只支持 3 选项节点。可先切回 3 选项再补写，或直接补写正文。
                </p>
              </template>
              <p v-else class="rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs text-paper-700/78">结局节点无 choices，可直接编辑结局 scene。</p>
            </div>
          </aside>
        </section>

        <section class="workbench-actions space-y-3 rounded-2xl border border-paper-200 bg-white/88 p-4">
          <div class="flex flex-wrap gap-2">
            <input v-model="form.storyId" class="w-44 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs" placeholder="故事 ID（可空）" />
            <input v-model="form.summary" class="min-w-44 flex-1 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs" placeholder="书城摘要" />
            <input v-model="form.sortOrder" class="w-32 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs" placeholder="排序值" />
            <input v-model="form.role" class="w-36 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs" placeholder="玩家身份" />
            <select v-model="form.provider" class="w-44 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-xs">
              <option value="volcengine">AI：Volcengine</option>
              <option value="secondme">AI：SecondMe</option>
            </select>
            <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800 disabled:opacity-55" :disabled="aiWorking" @click="aiCompleteNode('scene')">
              {{ aiWorking ? "补写中..." : "AI 补写正文" }}
            </button>
            <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800 disabled:opacity-55" :disabled="aiWorking" @click="aiCompleteNode('choices')">
              {{ aiWorking ? "补写中..." : "AI 补写选项" }}
            </button>
            <button class="active-press rounded-xl border border-paper-300 bg-white px-3 py-2 text-xs font-semibold text-paper-800 disabled:opacity-55" :disabled="aiWorking" @click="aiCompleteNode('both')">
              {{ aiWorking ? "补写中..." : "AI 补写整节点" }}
            </button>
            <button class="active-press rounded-xl bg-paper-900 px-4 py-2 text-xs font-semibold text-paper-50 disabled:opacity-55" :disabled="importing" @click="handlePublishToLibrary">
              {{ importing ? "发布中..." : "发布到公共书城" }}
            </button>
            <button class="active-press rounded-xl border border-red-300 bg-white px-4 py-2 text-xs font-semibold text-red-700 disabled:opacity-55" :disabled="deleting" @click="handleDeleteImported">
              {{ deleting ? "删除中..." : "删除导入故事" }}
            </button>
            <button class="active-press rounded-xl border border-paper-300 bg-white px-4 py-2 text-xs font-semibold text-paper-800" @click="backToMarket">
              返回逛书市
            </button>
          </div>
          <p class="rounded-xl bg-paper-50 px-3 py-2 text-[0.72rem] text-paper-700/80">NP 触发建议：太子、裴寂、将军好感同时 > 70。</p>
          <p v-if="success" class="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{{ success }}</p>
          <p v-if="error" class="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
          <section v-if="deleteReceipt" class="space-y-1 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2">
            <p class="text-xs font-semibold tracking-[0.08em] text-paper-700/70">删除回执</p>
            <pre class="whitespace-pre-wrap break-all text-[0.7rem] leading-5 text-paper-800">{{ JSON.stringify(deleteReceipt, null, 2) }}</pre>
          </section>
        </section>

        <section class="workbench-bottom-grid">
          <section class="workbench-json space-y-2 rounded-2xl border border-paper-200 bg-white/88 p-4">
            <h2 class="font-serif text-lg font-semibold text-paper-900">Story Package 预览 JSON</h2>
            <textarea class="min-h-[16rem] w-full resize-y rounded-2xl border border-paper-200 bg-paper-50 px-4 py-3 font-mono text-[0.68rem] leading-5 text-paper-900" :value="packagePreview" readonly />
          </section>

          <section class="workbench-cache space-y-2 rounded-2xl border border-paper-200 bg-white/88 p-4">
            <div class="flex items-center justify-between">
              <h2 class="font-serif text-lg font-semibold text-paper-900">书市缓存列表（含 ID）</h2>
              <button class="active-press rounded-lg border border-paper-300 bg-white px-3 py-1 text-xs font-semibold text-paper-700" @click="refreshImportedRows">刷新</button>
            </div>
            <p v-if="loadingRows" class="text-xs text-paper-700/65">正在加载...</p>
            <div v-else-if="libraryRows.length" class="max-h-[16rem] space-y-2 overflow-y-auto">
              <div v-for="row in libraryRows" :key="row.id" class="rounded-xl border border-paper-200 bg-paper-50 px-3 py-2">
                <p class="text-sm font-semibold text-paper-900">{{ row.title || "未命名" }}</p>
                <p class="mt-1 break-all font-mono text-xs text-paper-700/75">{{ row.id }}</p>
                <div v-if="String(row.id || '').startsWith('library-import-')" class="mt-2 flex gap-2">
                  <button class="active-press rounded-lg border border-red-300 bg-white px-2 py-1 text-xs font-semibold text-red-700" :disabled="deleting" @click="deleteByStoryId(row.id)">删除这条</button>
                </div>
              </div>
            </div>
            <p v-else class="text-xs text-paper-700/65">暂无书市缓存数据</p>
          </section>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.workbench-shell-desktop {
  position: relative;
  width: min(1600px, calc(100vw - 1.25rem));
  min-height: calc(100vh - 1.25rem);
  margin: 0.625rem auto;
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 28px;
  background: rgba(253, 251, 247, 0.96);
  box-shadow: 0 24px 80px rgba(61, 48, 38, 0.12);
  overflow: hidden;
}

.workbench-shell-desktop::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.2;
  background-image:
    radial-gradient(rgba(132, 102, 77, 0.06) 0.7px, transparent 0.7px),
    radial-gradient(rgba(255, 255, 255, 0.5) 0.7px, transparent 0.7px);
  background-size: 16px 16px, 22px 22px;
  background-position: 0 0, 11px 11px;
}

.workbench-shell-desktop::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 88% 14%, rgba(245, 158, 11, 0.12), transparent 24%),
    radial-gradient(circle at 14% 84%, rgba(239, 184, 184, 0.14), transparent 24%);
  filter: blur(32px);
}

.workflow-layout {
  display: grid;
  gap: 1rem;
  grid-template-columns: minmax(17rem, 22rem) minmax(0, 1fr) minmax(22rem, 28rem);
  align-items: start;
}

.workflow-pane {
  min-height: 20rem;
}

.workflow-left {
  position: sticky;
  top: 0.5rem;
}

.workflow-inspector {
  position: sticky;
  top: 0.5rem;
  max-height: calc(100vh - 7rem);
  overflow-y: auto;
}

.workflow-node {
  transition: box-shadow 120ms ease, border-color 120ms ease, transform 120ms ease;
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.workflow-node:hover {
  box-shadow: 0 8px 20px rgba(74, 59, 50, 0.12);
}

.workflow-node:active {
  cursor: grabbing;
}

.workflow-node-ending {
  border-style: dashed;
}

.workflow-node-drop-target {
  border-color: rgba(217, 119, 6, 0.7);
  box-shadow: 0 0 0 2px rgba(251, 191, 36, 0.26);
}

.workflow-handle {
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 20;
}

.workflow-handle-input {
  width: 0.72rem;
  height: 0.72rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 124, 108, 0.6);
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.8);
  pointer-events: none;
}

.workflow-handle-input-hover {
  border-color: rgba(217, 119, 6, 0.8);
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.26);
}

.workflow-handle-output {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 124, 108, 0.7);
  background: rgba(255, 255, 255, 0.98);
  color: rgba(74, 59, 50, 0.88);
  font-size: 0.58rem;
  font-weight: 600;
  line-height: 1;
  cursor: crosshair;
  transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}

.workflow-handle-output:hover {
  border-color: rgba(217, 119, 6, 0.85);
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.22);
  transform: translate(-50%, -50%) scale(1.06);
}

.workbench-bottom-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: minmax(0, 1fr) minmax(0, 24rem);
}

@media (max-width: 1279px) {
  .workflow-layout {
    grid-template-columns: 1fr;
  }

  .workflow-left,
  .workflow-inspector {
    position: static;
    max-height: none;
  }

  .workbench-bottom-grid {
    grid-template-columns: 1fr;
  }
}
</style>
