<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: "正在生成故事"
  },
  description: {
    type: String,
    default: "土豆正在认真酝酿下一段剧情，请稍候。"
  }
});
</script>

<template>
  <transition name="fade">
    <div
      v-if="visible"
      class="pointer-events-none fixed inset-0 z-[20] flex items-center justify-center bg-paper-900/12 px-6 backdrop-blur-[2px]"
    >
      <div class="glass-panel w-full max-w-[17rem] rounded-[28px] px-6 py-6 text-center shadow-[0_10px_40px_-10px_rgba(74,59,50,0.2)]">
        <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-paper-50 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
          <div class="loading-orb">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
        <p class="font-serif text-[1.3rem] font-semibold text-paper-900">{{ title }}</p>
        <p class="mt-2 text-sm leading-6 text-paper-700/75">{{ description }}</p>
        <div class="mt-4 flex items-center justify-center gap-2 text-paper-700/60">
          <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
      </div>
    </div>
  </transition>
</template>
