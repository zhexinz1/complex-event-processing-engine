import { onMounted, onUnmounted, ref } from 'vue';

export function useClock() {
  const currentTime = ref('');
  let clockTimer: ReturnType<typeof setInterval> | undefined;

  function updateClock() {
    const now = new Date();
    const options: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    };
    currentTime.value = now.toLocaleString('zh-CN', options).replace(/\//g, '-');
  }

  onMounted(() => {
    updateClock();
    clockTimer = setInterval(updateClock, 1000);
  });

  onUnmounted(() => {
    if (clockTimer) {
      clearInterval(clockTimer);
    }
  });

  return {
    currentTime,
  };
}
