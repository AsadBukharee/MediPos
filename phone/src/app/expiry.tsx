import { useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { Badge, Card, Empty, Notice, OfflineBanner, Row, text } from '@/components/ui';
import { formatDate, useResource } from '@/lib/hooks';
import { colors, radius, space } from '@/lib/theme';

interface ExpiryRow {
  batch: number;
  name: string;
  batch_number: string;
  expiry_date: string;
  days_left: number;
  quantity: number;
}

const WINDOWS: [string, string][] = [
  ['30', '30 days'],
  ['60', '60 days'],
  ['90', '90 days'],
  ['expired', 'Expired'],
];

export default function ExpiryScreen() {
  const [window, setWindow] = useState('30');
  const expired = window === 'expired';
  const report = useResource<{ rows: ExpiryRow[] }>('/reports/inventory/', expired ? { report: 'expired' } : { report: 'near_expiry', days: window });

  return (
    <FlatList
      data={report.data?.rows ?? []}
      keyExtractor={(row) => String(row.batch)}
      contentContainerStyle={{ padding: space.lg, gap: space.sm }}
      refreshControl={<RefreshControl refreshing={report.loading} onRefresh={report.reload} tintColor={colors.brand} />}
      ListHeaderComponent={
        <View style={{ gap: space.md, marginBottom: space.sm }}>
          <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }} accessibilityRole="tablist">
            {WINDOWS.map(([value, label]) => (
              <Pressable
                key={value}
                accessibilityRole="tab"
                accessibilityState={{ selected: window === value }}
                onPress={() => setWindow(value)}
                style={{
                  minHeight: 44, justifyContent: 'center', paddingHorizontal: space.md, borderRadius: radius.lg, borderWidth: 1,
                  backgroundColor: window === value ? colors.ink : colors.surface, borderColor: window === value ? colors.ink : colors.line,
                }}>
                <Text style={{ color: window === value ? colors.white : colors.muted, fontWeight: '600' }}>{label}</Text>
              </Pressable>
            ))}
          </View>
          <OfflineBanner stale={report.stale} savedAt={report.savedAt} />
          <Notice text={report.error} />
        </View>
      }
      renderItem={({ item }) => (
        <Card>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: space.sm }}>
            <Text style={[text.heading, { flex: 1 }]}>{item.name}</Text>
            <Badge label={item.days_left <= 0 ? 'Expired' : `${item.days_left} days`} tone={item.days_left <= 0 ? 'danger' : 'warn'} />
          </View>
          <Row label={`Batch ${item.batch_number}`} value={formatDate(item.expiry_date)} />
          <Row label="Quantity" value={item.quantity} />
        </Card>
      )}
      ListEmptyComponent={report.loading || report.error ? undefined : <Empty text={expired ? 'No expired stock on the shelf.' : 'Nothing expires in this window.'} />}
    />
  );
}
