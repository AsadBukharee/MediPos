import { useRouter } from 'expo-router';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { Button, Card, Notice, OfflineBanner, Row, text } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { formatMoney, useResource } from '@/lib/hooks';
import { colors, space } from '@/lib/theme';
import type { Dashboard } from '@/lib/types';

export default function MoreScreen() {
  const router = useRouter();
  const { user, branch, can, signOut, chooseBranch } = useAuth();
  const dashboard = useResource<Dashboard>(can('reports.view') ? '/reports/dashboard/' : null);
  const unread = useResource<{ unread: number }>('/notifications/unread-count/');
  const data = dashboard.data;

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }}>
      <View>
        <Text style={text.title}>{user?.first_name || user?.username}</Text>
        <Text style={text.muted}>
          {user?.role.replace(/_/g, ' ')} · {branch?.name}
        </Text>
      </View>

      {can('reports.view') && (
        <Card>
          <Text style={text.heading}>Today at {branch?.name}</Text>
          <OfflineBanner stale={dashboard.stale} savedAt={dashboard.savedAt} />
          <Notice text={dashboard.error} />
          {data && (
            <>
              <Row label="Sales today" value={`${formatMoney(data.today_sales)} (${data.today_invoices})`} />
              <Row label="Revenue this month" value={formatMoney(data.month_revenue)} />
              <Row label="Gross profit this month" value={formatMoney(data.month_gross_profit)} tone="ok" />
              <Row label="Stock value" value={formatMoney(data.stock_value)} />
              <Row label="Low stock" value={data.low_stock_count} tone="warn" />
              <Row label="Out of stock" value={data.out_of_stock_count} tone="danger" />
              <Row label="Expiring in 30 days" value={data.near_expiry_count} tone="warn" />
              <Row label="Expired batches" value={data.expired_count} tone="danger" />
            </>
          )}
        </Card>
      )}

      <Link label="Notifications" detail={unread.data?.unread ? `${unread.data.unread} unread` : 'All read'} onPress={() => router.push('/notifications')} />
      {can('inventory.view') && <Link label="Expiry" detail="Batches expiring soon or expired" onPress={() => router.push('/expiry')} />}

      {(user?.branches.length ?? 0) > 1 && (
        <Card>
          <Text style={text.heading}>Switch branch</Text>
          {user?.branches.map((b) => (
            <Button key={b.id} title={b.name} variant={b.id === branch?.id ? 'primary' : 'secondary'} compact onPress={() => chooseBranch(b)} />
          ))}
        </Card>
      )}
      <Button title="Sign out" variant="secondary" onPress={signOut} />
    </ScrollView>
  );
}

function Link({ label, detail, onPress }: { label: string; detail: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress}>
      <Card style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View>
          <Text style={text.heading}>{label}</Text>
          <Text style={text.muted}>{detail}</Text>
        </View>
        <Text style={{ color: colors.muted, fontSize: 20 }}>›</Text>
      </Card>
    </Pressable>
  );
}
