import { useRouter } from 'expo-router';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { Button, Empty, Notice, OfflineBanner, text } from '@/components/ui';
import { api } from '@/lib/api';
import { useResource } from '@/lib/hooks';
import { colors, radius, space } from '@/lib/theme';
import type { AppNotification, Paginated } from '@/lib/types';

export default function NotificationsScreen() {
  const router = useRouter();
  const history = useResource<Paginated<AppNotification>>('/notifications/', { page_size: 60 });
  const reload = history.reload;

  const open = async (item: AppNotification) => {
    if (!item.is_read) await api(`/notifications/${item.id}/read/`, { method: 'POST' }).catch(() => undefined);
    if (item.data.alert_id) router.push({ pathname: '/alerts/[id]', params: { id: String(item.data.alert_id) } });
    else if (item.type === 'near_expiry' || item.type === 'expired_stock') router.push('/expiry');
    else if (item.type === 'purchase_approval') router.push('/orders');
    else reload();
  };
  const readAll = async () => {
    await api('/notifications/read-all/', { method: 'POST' }).catch(() => undefined);
    reload();
  };

  return (
    <FlatList
      data={history.data?.results ?? []}
      keyExtractor={(item) => String(item.id)}
      contentContainerStyle={{ padding: space.lg, gap: space.sm }}
      refreshControl={<RefreshControl refreshing={history.loading} onRefresh={reload} tintColor={colors.brand} />}
      ListHeaderComponent={
        <View style={{ gap: space.sm, marginBottom: space.sm }}>
          <OfflineBanner stale={history.stale} savedAt={history.savedAt} />
          <Notice text={history.error} />
          {history.data?.results.some((n) => !n.is_read) && <Button title="Mark all as read" variant="secondary" compact onPress={readAll} />}
        </View>
      }
      renderItem={({ item }) => (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${item.is_read ? '' : 'Unread. '}${item.title}`}
          onPress={() => open(item)}
          style={{
            backgroundColor: item.is_read ? colors.surface : colors.brandSoft, borderRadius: radius.md, borderWidth: 1,
            borderColor: item.is_read ? colors.line : colors.brand, padding: space.md, gap: 2,
          }}>
          <Text style={[text.heading, { fontWeight: item.is_read ? '500' : '700' }]}>{item.title}</Text>
          {item.body ? <Text style={text.body}>{item.body}</Text> : null}
          <Text style={text.muted}>
            {new Date(item.created_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </Text>
        </Pressable>
      )}
      ListEmptyComponent={history.loading || history.error ? undefined : <Empty text="No notifications yet." />}
    />
  );
}
