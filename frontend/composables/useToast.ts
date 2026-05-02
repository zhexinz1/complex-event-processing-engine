import { ref } from 'vue';
import type { ShowToast, ToastType } from '../types';

const toast = ref<{ show: boolean; message: string; type: ToastType }>({
  show: false,
  message: '',
  type: 'success',
});

let hideTimer: ReturnType<typeof setTimeout> | null = null;

export function useToast() {
  const showToast: ShowToast = (message, type = 'success') => {
    if (hideTimer) {
      clearTimeout(hideTimer);
    }
    toast.value = { show: true, message, type };
    hideTimer = setTimeout(() => {
      toast.value.show = false;
      hideTimer = null;
    }, 3000);
  };

  return {
    toast,
    showToast,
  };
}
