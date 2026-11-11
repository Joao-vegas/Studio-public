// Registro de todas as cenas 3D (nome usado no short3d*.json → componente). Só soma os grupos: cada agente edita o SEU arquivo.
// Cenas de EXEMPLO do S001 (Tesla Roadster no espaço): grupos A, B, C, D. Cena em branco para copiar: CenaModelo.
import React from 'react';
import {CENAS_3D} from './Cenas3D';   // grupo A: cenas 1, 2, 6, 7 e 13 (dono dos modelos Carro e Starman)
import {CENAS_B} from './CenasB';     // grupo B: cenas 3, 4 e 5
import {CENAS_C} from './CenasC';     // grupo C: cenas 8 e 9
import {CENAS_D} from './CenasD';     // grupo D: cenas 10, 11 e 12
import {CENAS_E} from './CenasE-otica';  // grupo E: Cliente2 OL32 "Ótica por dentro" (a ótica, a rua, a gaveta, o pack)
import {CenaModelo} from './CenaModelo';
export const REGISTRO_3D: Record<string, React.FC> = {modelo: CenaModelo, ...CENAS_3D, ...CENAS_B, ...CENAS_C, ...CENAS_D, ...CENAS_E};
