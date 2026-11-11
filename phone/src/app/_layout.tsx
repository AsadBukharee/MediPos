import { Stack, useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { AuthProvider, useAuth } from '@/lib/auth';
import { targetOf } from '@/lib/push';
import { colors } from '@/lib/theme';

SplashScreen.preventAutoHideAsync();

function Navigator() {
  const { ready, user, branch } = useAuth();
  const router = useRouter();
  const signedIn = Boolean(user);
  const lastResponse = Notifications.useLastNotificationResponse();

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  // Deep links from notifications: tapping one (or its action buttons) opens the alert it is about.
  useEffect(() => {
    if (!lastResponse || !signedIn || !branch) return;
    const target = targetOf(lastResponse);
    if (target.alertId) {
      router.push({ pathname: '/alerts/[id]', params: { id: String(target.alertId), action: target.action } });
    } else if (target.url?.includes('expiry')) {
      router.push('/expiry');
    } else {
      router.push('/notifications');
    }
    Notifications.clearLastNotificationResponse();
  }, [lastResponse, signedIn, branch, router]);

  if (!ready) return null;
  const header = { headerStyle: { backgroundColor: colors.ink }, headerTintColor: colors.white, contentStyle: { backgroundColor: colors.canvas } };
  return (
    <Stack screenOptions={header}>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && !branch}>
        <Stack.Screen name="branch" options={{ title: 'Choose a branch' }} />
      </Stack.Protected>
      <Stack.Protected guard={signedIn && Boolean(branch)}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="product/[id]" options={{ title: 'Stock & batches' }} />
        <Stack.Screen name="alerts/[id]" options={{ title: 'Stock alert' }} />
        <Stack.Screen name="notifications" options={{ title: 'Notifications' }} />
        <Stack.Screen name="expiry" options={{ title: 'Expiry' }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="light" />
      <Navigator />
    </AuthProvider>
  );
}
