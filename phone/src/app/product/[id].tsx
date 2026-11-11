import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { Badge, Button, Card, Empty, Field, Notice, OfflineBanner, Row, text } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { daysUntil, formatDate, formatMoney, useAction, useResource } from '@/lib/hooks';
import { space } from '@/lib/theme';
import type { Batch, StockRow } from '@/lib/types';

export default function ProductScreen() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const { can } = useAuth();
  const stock = useResource<StockRow>(`/inventory/stock/${id}/`);
  const batches = useResource<Batch[]>(`/inventory/stock/${id}/batches/`);
  const [reporting, setReporting] = useState<Batch | null>(null);
  const row = stock.data;
  const unit = row?.base_unit_name.toLowerCase() ?? 'unit';

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }} keyboardShouldPersistTaps="handled">
      <Stack.Screen options={{ title: row ? `${row.name} ${row.strength}` : (name ?? 'Stock & batches') }} />
      <OfflineBanner stale={stock.stale || batches.stale} savedAt={stock.savedAt} />
      <Notice text={stock.error ?? batches.error} />
      {row && (
        <Card>
          <Text style={text.title}>
            {row.name} <Text style={{ fontWeight: '400' }}>{row.strength}</Text>
          </Text>
          {row.generic_name ? <Text style={text.muted}>{row.generic_name}</Text> : null}
          <Row label="Sellable now" value={`${row.sellable} ${unit}(s)`} tone={row.state === 'out' ? 'danger' : row.state === 'low' ? 'warn' : 'ok'} />
          <Row label="On hand (all batches)" value={row.on_hand} />
          <Row label="Reorder level" value={row.reorder_level || '—'} />
          <Row label={`Price per ${unit}`} value={formatMoney(row.retail_price)} />
          <Row label="SKU" value={row.sku} />
        </Card>
      )}

      <Text style={text.heading}>Batches</Text>
      {(batches.data ?? []).map((batch) => {
        const left = daysUntil(batch.expiry_date);
        return (
          <Card key={batch.id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={text.heading}>{batch.batch_number}</Text>
              {batch.is_expired ? (
                <Badge label="Expired" tone="danger" />
              ) : batch.status !== 'active' ? (
                <Badge label={batch.status} tone="danger" />
              ) : left <= 90 ? (
                <Badge label={`${left} days left`} tone="warn" />
              ) : (
                <Badge label="OK" tone="ok" />
              )}
            </View>
            <Row label="Expiry" value={formatDate(batch.expiry_date)} />
            <Row label="Quantity" value={`${batch.quantity_on_hand} ${unit}(s)`} />
            {can('inventory.adjust') && !batches.stale && (
              <Button title="Report damaged or lost stock" variant="secondary" compact onPress={() => setReporting(batch)} />
            )}
            {reporting?.id === batch.id && <AdjustmentRequest batch={batch} unit={unit} onClose={() => setReporting(null)} />}
          </Card>
        );
      })}
      {!batches.loading && (batches.data?.length ?? 0) === 0 && <Empty text="No stock of this medicine in this branch." />}
    </ScrollView>
  );
}

/** Sends a stock adjustment request. Stock only changes after a manager approves it. */
function AdjustmentRequest({ batch, unit, onClose }: { batch: Batch; unit: string; onClose: () => void }) {
  const [quantity, setQuantity] = useState('');
  const [note, setNote] = useState('');
  const [sent, setSent] = useState(false);
  const { busy, error, run } = useAction();
  const amount = Number(quantity);
  const send = async (reason: 'damaged' | 'lost') => {
    const done = await run(() =>
      api('/inventory/adjustments/', { body: { reason, note, items: [{ batch: batch.id, quantity_delta: -amount }] } }),
    );
    if (done) setSent(true);
  };
  if (sent) return <Notice tone="ok" text="Request sent. A manager has to approve it before stock changes." />;
  return (
    <View style={{ gap: space.sm }}>
      <Notice text={error} />
      <Field label={`How many ${unit}s?`} value={quantity} onChangeText={(v) => setQuantity(v.replace(/\D/g, ''))} keyboardType="number-pad" inputMode="numeric" />
      <Field label="Note" value={note} onChangeText={setNote} placeholder="What happened?" />
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <View style={{ flex: 1 }}>
          <Button title="Damaged" busy={busy} disabled={!(amount > 0) || amount > batch.quantity_on_hand} onPress={() => send('damaged')} />
        </View>
        <View style={{ flex: 1 }}>
          <Button title="Lost" variant="secondary" disabled={busy || !(amount > 0) || amount > batch.quantity_on_hand} onPress={() => send('lost')} />
        </View>
      </View>
      <Button title="Cancel" variant="ghost" compact onPress={onClose} />
    </View>
  );
}
