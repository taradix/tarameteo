// The native map can't render under jest-expo: the map is a View tests drive with fireEvent
// (regionChangeComplete, press), and pins are buttons labelled like the real ones.
import { forwardRef, useImperativeHandle, type ReactNode } from "react";
import { Pressable, View, type ViewProps } from "react-native";

type Region = { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number };
type MapProps = ViewProps & { onRegionChangeComplete?: (region: Region) => void };

// Animating ends where the real map would: a region change.
const MapView = forwardRef<unknown, MapProps>(function MapView(props, ref) {
  useImperativeHandle(ref, () => ({ animateToRegion: (region: Region) => props.onRegionChangeComplete?.(region) }));
  return <View {...props} />;
});
export default MapView;

type MarkerProps = { accessibilityLabel?: string; onPress?: () => void; children?: ReactNode };

export function Marker({ accessibilityLabel, onPress, children }: MarkerProps) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel} onPress={onPress}>
      {children}
    </Pressable>
  );
}
