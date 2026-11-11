import {Composition} from 'remotion';
import {Short3D, Short3DProps, defaultShort3D} from './Short3D';

const metaS3 = ({props}: {props: Short3DProps}) => ({durationInFrames: Math.max(1, props.total), fps: props.fps});

export const Root = () => (
  <Composition id="Short3D" component={Short3D} width={1080} height={1920} fps={30} durationInFrames={150}
    defaultProps={defaultShort3D} calculateMetadata={metaS3} />
);
