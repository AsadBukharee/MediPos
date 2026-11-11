import { Tabs } from 'expo-router/js-tabs';
import { Text, type ColorValue } from 'react-native';

import { useAuth } from '@/lib/auth';
import { colors } from '@/lib/theme';

const icon = (glyph: string) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ color, fontSize: 20 }}>{glyph}</Text>;
  };

export default function TabsLayout() {
  const { can, branch } = useAuth();
  // Role-based screens: a tab only exists for roles that can use it.
  const hidden = (permission: string) => (can(permission) ? undefined : null);
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.ink },
        headerTintColor: colors.white,
        headerTitleAlign: 'left',
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.muted,
        sceneStyle: { backgroundColor: colors.canvas },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Alerts', headerTitle: `Stock alerts · ${branch?.name ?? ''}`, tabBarIcon: icon('◔'), href: hidden('inventory.view') }} />
      <Tabs.Screen name="search" options={{ title: 'Search', headerTitle: 'Find a medicine', tabBarIcon: icon('⌕'), href: hidden('inventory.view') }} />
      <Tabs.Screen name="scan" options={{ title: 'Scan', headerTitle: 'Scan a barcode', tabBarIcon: icon('▥'), href: hidden('catalog.view') }} />
      <Tabs.Screen name="orders" options={{ title: 'Orders', headerTitle: 'Order list', tabBarIcon: icon('☰'), href: hidden('purchases.view') }} />
      <Tabs.Screen name="more" options={{ title: 'More', headerTitle: 'More', tabBarIcon: icon('⋯') }} />
    </Tabs>
  );
}
