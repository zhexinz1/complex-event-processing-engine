import { ref } from 'vue';
import type { ShowToast, ToastType } from '../types';

export function useToast() {
  const toast = ref<{ show: boolean; message: string; type: ToastType }>({
    show: false,
    message: '',
    type: 'success',
  });

  const showToast: ShowToast = (message, type = 'success') => {
    toast.value = { show: true, message, type };
    setTimeout(() => {
      toast.value.show = false;
    }, 3000);
  };

  return {
    toast,
    showToast,
  };
}
