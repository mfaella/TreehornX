#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>



enum PC {
    LEFT_CALL_PC,
    RIGHT_CALL_PC
};

enum BF {
    HIGH_LEFT, LOW_LEFT, NEUTRAL, LOW_RIGHT, HIGH_RIGHT
};

struct Node {
    int data;
    enum BF bf;                  // balance factor, kept in {-1, 0, +1} */
    enum PC pc;
    struct Node *left;
    struct Node *right;
    struct Node *parent;
};

void avl_safe_insert(struct Node *root, int key)
{
    struct Node *result_node;
    struct Node *z;
    struct Node *y;
    struct Node *tmp;
    struct Node *tmp2;
    struct Node *parent;
    struct Node *current;
    _Bool result_grew;
    enum PC tmp_pc;
    enum BF tmp_bf;

    int tmp_data;
    current = root;
    // 1. Empty slot reached -> create the new leaf. */

    START:
    if (!current) {
        result_node = malloc(sizeof (struct Node));
        result_node->data  = key;
        result_node->bf   = NEUTRAL;
        result_grew = true;
        goto MyReturn;
    }

    tmp_data = current->data;
    if (key < tmp_data) {
        parent = current;
        current->pc = LEFT_CALL_PC;
        current = current->left;

        goto START;

        LeftCallEnd:

        current->left = result_node;
        if (!result_grew) {             // left height unchanged -> done */
            result_grew = false;
            result_node = current;
            goto MyReturn;
        }
        tmp_bf = current->bf;
        if(tmp_bf == LOW_RIGHT) {
            current->bf = NEUTRAL;
        }
        else if(tmp_bf == NEUTRAL) {
            current->bf = LOW_LEFT;
        }
        else {
            current->bf = HIGH_LEFT;                   // left side became taller */
        }
    } else if (key > tmp_data) {

        parent = current;
        current->pc = RIGHT_CALL_PC;
        current = current->right;

        goto START;

        RightCallEnd:

        current->right = result_node;
        if (!result_grew) {             // right height unchanged -> done */
            result_grew = false;
            result_node = current;
            goto MyReturn;
        }

        tmp_bf = current->bf;
        if (tmp_bf == LOW_LEFT) {
            current->bf = NEUTRAL;
        }
        else if (tmp_bf == NEUTRAL) {
            current->bf = LOW_RIGHT;
        }
        else {
            current->bf = HIGH_RIGHT;
        }                   // right side became taller */
    } else {
        result_grew = false;                     // duplicate key: ignore */
        result_node = current;
        goto MyReturn;
    }

    // 3. Interpret the updated balance factor of this node. */
    tmp_bf = current->bf;
    if (tmp_bf == NEUTRAL) {
        // The previously shorter side caught up: subtree height unchanged. */
        result_grew = false;
        result_node = current;
        goto MyReturn;
    }
    if (tmp_bf == LOW_LEFT || tmp_bf == LOW_RIGHT) {
        // Still AVL-valid but one level taller: keep propagating upward. */
        result_grew = true;
        result_node = current;
        goto MyReturn;
    }

    // 4. bf is +2 or -2: rebalance with a rotation. An insertion rotation
    result_grew = false;

    if (tmp_bf == HIGH_RIGHT) {                 // right-heavy */
        z = current->right;
        tmp_bf = z->bf;
        if (tmp_bf == NEUTRAL || tmp_bf == LOW_RIGHT) {
            // ---- RR case: single LEFT rotation ---- */
            z->bf = NEUTRAL;
            tmp = z->left;
            z->left = current;
            result_node = z;
            current->bf = NEUTRAL;
            current->right = tmp;
            goto MyReturn;
        } else {
            // ---- RL case: right rotation on z, then left rotation on node ---- */
            y = z->left;       // inner grandchild becomes new root */

            tmp = y->right;
            tmp2 = y->left;
            y->right = z;
            y->left = current;
            tmp_bf = y->bf;
            y->bf = NEUTRAL;
            result_node = y;
            z->left = tmp;
            if (tmp_bf == NEUTRAL) {            // y was the inserted node itself */
                z->bf    = NEUTRAL;
            } else if (tmp_bf == LOW_RIGHT) {      // y's right subtree was the tall one */
                z->bf    = NEUTRAL;
            } else {                     // y's left subtree was the tall one */
                z->bf    = LOW_RIGHT;
            }
            current->right = tmp2;
            if (tmp_bf == NEUTRAL) {            // y was the inserted node itself */
                current->bf = NEUTRAL;
            } else if (tmp_bf == LOW_RIGHT) {      // y's right subtree was the tall one */
                current->bf = LOW_LEFT;
            } else {                     // y's left subtree was the tall one */
                current->bf = NEUTRAL;
            }
            goto MyReturn;
        }
    } else {                             // node->bf == -2, left-heavy */
        z = current->left;
        tmp_bf = z->bf;
        if (tmp_bf == NEUTRAL || tmp_bf == LOW_LEFT) {
            // ---- LL case: single RIGHT rotation ---- */
            tmp = z->right;
            z->right   = current;
            z->bf    = NEUTRAL;
            result_node = z;
            current->left = tmp;
            current->bf = NEUTRAL;
            goto MyReturn;
        } else {
            // ---- LR case: left rotation on z, then right rotation on node ---- */
            y = z->right;      // inner grandchild becomes new root */
            tmp = y->left;
            tmp2 = y->right;
            y->left = z;
            y->right = current;
            tmp_bf = y->bf;
            y->bf = NEUTRAL;
            result_node = y;
            z->right = tmp;
            if (tmp_bf == NEUTRAL) {
                z->bf    = NEUTRAL;
            } else if (tmp_bf == LOW_LEFT) {      // y's left subtree was the tall one */
                z->bf    = NEUTRAL;
            } else {                     // y's right subtree was the tall one */
                z->bf    = LOW_LEFT;
            }
            current->left = tmp2;
            if (tmp_bf == NEUTRAL) {
                current->bf = NEUTRAL;
            } else if (tmp_bf == LOW_LEFT) {      // y's left subtree was the tall one */
                current->bf = LOW_RIGHT;
            } else {                     // y's right subtree was the tall one */
                current->bf = NEUTRAL;
            }
            goto MyReturn;
        }
    }
    MyReturn:
    if (current) {
        parent = current->parent;
    }
    if(parent) {
        tmp_pc = parent->pc;
        current = parent;
        if(tmp_pc == LEFT_CALL_PC) {
            goto LeftCallEnd;
        }
        else {
            goto RightCallEnd;
        }
    }
    else {
        root = result_node;
    }

}
