import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { AndroidImportance } from 'expo-notifications';
import { Platform } from 'react-native';

import { api } from './api';

export const STOCK_ALERT_CATEGORY = 'stock_alert';
export const ACTION_ADD = 'add_to_order';
export const ACTION_SKIP = 'skip';

let registeredToken: string | null = null;

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/** Channels and the "Add to Order List / Skip" action buttons shown on stock alerts. */
export async function configureNotifications() {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('stock-alerts', {
      name: 'Stock alerts',
      importance: AndroidImportance.HIGH,
    });
    await Notifications.setNotificationChannelAsync('general', {
      name: 'General',
      importance: AndroidImportance.DEFAULT,
    });
  }
  await Notifications.setNotificationCategoryAsync(STOCK_ALERT_CATEGORY, [
    { identifier: ACTION_ADD, buttonTitle: 'Add to Order List', options: { opensAppToForeground: true } },
    { identifier: ACTION_SKIP, buttonTitle: 'Skip', options: { opensAppToForeground: true } },
  ]);
}

/** Ask for permission and hand this device's FCM token to the server. */
export async function registerForPush(): Promise<boolean> {
  if (!Device.isDevice) return false; // emulators without Play services have no token
  await configureNotifications();
  let { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') status = (await Notifications.requestPermissionsAsync()).status;
  if (status !== 'granted') return false;
  const token = await Notifications.getDevicePushTokenAsync();
  if (typeof token.data !== 'string') return false;
  await api('/notifications/devices/', { body: { token: token.data, platform: Platform.OS } });
  registeredToken = token.data;
  return true;
}

export async function unregisterPush() {
  if (!registeredToken) return;
  await api('/notifications/devices/', { method: 'DELETE', body: { token: registeredToken } });
  registeredToken = null;
}

export interface PushTarget {
  alertId?: number;
  notificationId?: number;
  action: 'open' | 'add' | 'skip';
  url?: string;
}

/** Work out where a tapped notification (or one of its action buttons) should take the user. */
export function targetOf(response: Notifications.NotificationResponse): PushTarget {
  const data = (response.notification.request.content.data ?? {}) as Record<string, unknown>;
  const number = (value: unknown) => (value === undefined || value === null || value === '' ? undefined : Number(value));
  const action =
    response.actionIdentifier === ACTION_ADD ? 'add' : response.actionIdentifier === ACTION_SKIP ? 'skip' : 'open';
  return {
    alertId: number(data.alert_id),
    notificationId: number(data.notification_id),
    action,
    url: typeof data.url === 'string' ? data.url : undefined,
  };
}
