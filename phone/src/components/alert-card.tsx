import { useState } from 'react';
import { Text, View } from 'react-native';

import { Badge, Button, Card, Field, Notice, Row, text } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useAction } from '@/lib/hooks';
import { space } from '@/lib/theme';
import type { StockAlert } from '@/lib/types';

const STATUS: Record<StockAlert['status'], { label: string; tone: 'warn' | 'brand' | 'neutral' | 'ok' }> = {
  open: { label: 'Needs a decision', tone: 'warn' },
  added: { label: 'On the order list', tone: 'brand' },
  skipped: { label: 'Skipped', tone: 'neutral' },
  resolved: { label: 'Stock recovered', tone: 'ok' },
};

/** A stock alert with its two actions: Add to Order List (with an editable quantity) and Skip. */
export function AlertCard({ alert, onChanged }: { alert: StockAlert; onChanged: (updated: StockAlert) => void }) {
  const { can } = useAuth();
  const [quantity, setQuantity] = useState(String(alert.requested_quantity ?? alert.suggested_quantity));
  const { busy, error, run } = useAction();
  const unit = alert.base_unit_name.toLowerCase();
  const actionable = can('alerts.act') && alert.status !== 'resolved';

  const act = async (action: 'add-to-order' | 'skip') => {
    const updated = await run(() =>
      api<StockAlert>(`/notifications/alerts/${alert.id}/${action}/`, {
        method: 'POST',
        body: action === 'add-to-order' ? { quantity: Number(quantity) } : {},
      }),
    );
    if (updated) onChanged(updated);
  };

  return (
    <Card>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: space.sm }}>
        <Text style={[text.heading, { flex: 1 }]}>{alert.product_name}</Text>
        <Badge label={alert.kind === 'out_of_stock' ? 'Out of stock' : 'Low stock'} tone={alert.kind === 'out_of_stock' ? 'danger' : 'warn'} />
      </View>
      <Row label="Left on the shelf" value={`${alert.triggered_quantity} ${unit}(s)`} tone={alert.kind === 'out_of_stock' ? 'danger' : 'warn'} />
      <Row label="Reorder level" value={alert.reorder_level} />
      <Row label="Suggested order" value={`${alert.suggested_quantity} ${unit}(s)`} />
      {alert.status !== 'open' && <Badge label={STATUS[alert.status].label} tone={STATUS[alert.status].tone} />}
      <Notice text={error} />
      {actionable && (
        <>
          <Field
            label={`Quantity to order (${unit}s)`}
            value={quantity}
            onChangeText={(value) => setQuantity(value.replace(/\D/g, ''))}
            keyboardType="number-pad"
            inputMode="numeric"
          />
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <View style={{ flex: 2 }}>
              <Button
                title={alert.status === 'added' ? 'Update quantity' : 'Add to Order List'}
                busy={busy}
                disabled={!(Number(quantity) > 0)}
                onPress={() => act('add-to-order')}
              />
            </View>
            {alert.status === 'open' && (
              <View style={{ flex: 1 }}>
                <Button title="Skip" variant="secondary" disabled={busy} onPress={() => act('skip')} />
              </View>
            )}
          </View>
        </>
      )}
    </Card>
  );
}
