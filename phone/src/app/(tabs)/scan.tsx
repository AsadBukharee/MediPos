import { CameraView, useCameraPermissions } from 'expo-camera';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';

import { Button, Notice, text } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { colors, radius, space } from '@/lib/theme';
import type { Product } from '@/lib/types';

export default function ScanScreen() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [active, setActive] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const busy = useRef(false);

  // The camera only runs while this tab is in front.
  useFocusEffect(
    useCallback(() => {
      setActive(true);
      busy.current = false;
      return () => setActive(false);
    }, []),
  );

  const onScanned = async ({ data }: { data: string }) => {
    if (busy.current) return; // the camera reports the same code many times a second
    busy.current = true;
    setMessage(null);
    try {
      const product = await api<Product>('/catalog/products/lookup/', { params: { barcode: data } });
      router.push({ pathname: '/product/[id]', params: { id: String(product.id), name: `${product.name} ${product.strength}` } });
    } catch (error) {
      const notFound = error instanceof ApiError && error.status === 404;
      setMessage(notFound ? `No medicine has the barcode ${data}.` : (error as Error).message);
      setTimeout(() => (busy.current = false), 1500);
    }
  };

  if (!permission) return <View style={styles.center} />;
  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={[text.heading, { textAlign: 'center' }]}>Camera access is needed to scan barcodes</Text>
        <Text style={[text.muted, { textAlign: 'center' }]}>The camera is only used for scanning. Nothing is recorded or stored.</Text>
        {permission.canAskAgain ? (
          <Button title="Allow camera" onPress={requestPermission} />
        ) : (
          <Button title="Open settings" onPress={() => Linking.openSettings()} />
        )}
      </View>
    );
  }
  return (
    <View style={{ flex: 1, backgroundColor: colors.ink }}>
      {active && (
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'itf14', 'qr', 'datamatrix'] }}
          onBarcodeScanned={onScanned}
        />
      )}
      <View pointerEvents="none" style={styles.overlay}>
        <View style={styles.frame} />
        <Text style={{ color: colors.white, fontSize: 15 }}>Point the camera at the barcode on the pack</Text>
      </View>
      <View style={{ position: 'absolute', left: space.lg, right: space.lg, bottom: space.xl }}>
        <Notice tone="warn" text={message} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'stretch', justifyContent: 'center', padding: space.xl, gap: space.lg, backgroundColor: colors.canvas },
  overlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, alignItems: 'center', justifyContent: 'center', gap: space.lg },
  frame: { width: '78%', height: 150, borderRadius: radius.lg, borderWidth: 2, borderColor: colors.white },
});
