import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { AlertCard } from '@/components/alert-card';
import { Empty, Notice, OfflineBanner } from '@/components/ui';
import { useResource } from '@/lib/hooks';
import { colors, radius, space } from '@/lib/theme';
import type { Paginated, StockAlert } from '@/lib/types';

const FILTERS: [StockAlert['status'], string][] = [
  ['open', 'To decide'],
  ['added', 'Added'],
  ['skipped', 'Skipped'],
];

export default function AlertsScreen() {
  const [status, setStatus] = useState<StockAlert['status']>('open');
  const alerts = useResource<Paginated<StockAlert>>('/notifications/alerts/', { status, page_size: 100 });
  const reload = alerts.reload;
  useFocusEffect(useCallback(() => reload(), [reload]));

  return (
    <FlatList
      data={alerts.data?.results ?? []}
      keyExtractor={(alert) => `${alert.id}-${alert.status}`}
      contentContainerStyle={{ padding: space.lg, gap: space.md }}
      refreshControl={<RefreshControl refreshing={alerts.loading} onRefresh={reload} tintColor={colors.brand} />}
      ListHeaderComponent={
        <View style={{ gap: space.md }}>
          <View style={{ flexDirection: 'row', gap: space.sm }} accessibilityRole="tablist">
            {FILTERS.map(([value, label]) => (
              <Pressable
                key={value}
                accessibilityRole="tab"
                accessibilityState={{ selected: status === value }}
                onPress={() => setStatus(value)}
                style={{
                  minHeight: 44, justifyContent: 'center', paddingHorizontal: space.lg, borderRadius: radius.lg,
                  backgroundColor: status === value ? colors.ink : colors.surface, borderWidth: 1, borderColor: status === value ? colors.ink : colors.line,
                }}>
                <Text style={{ color: status === value ? colors.white : colors.muted, fontWeight: '600' }}>{label}</Text>
              </Pressable>
            ))}
          </View>
          <OfflineBanner stale={alerts.stale} savedAt={alerts.savedAt} />
          <Notice text={alerts.error} />
        </View>
      }
      renderItem={({ item }) => <AlertCard alert={item} onChanged={reload} />}
      ListEmptyComponent={
        alerts.loading || alerts.error ? undefined : (
          <Empty text={status === 'open' ? 'No alerts waiting. Every medicine is above its reorder level, or already handled.' : 'Nothing here.'} />
        )
      }
    />
  );
}
