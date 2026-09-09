// C program to insert a node in AVL tree
#include <stdlib.h>
#include <stdio.h>

enum call_on_e { LEFT, RIGHT };

struct Node {
  int data;
  int height;
  struct Node *left;
  struct Node *right;
  struct Node *parent;
  enum call_on_e call_on;
};

// Recursive function to insert a key in the subtree rooted
// with node and returns the new root of the subtree.
void avl_safe_insert(struct Node *root, int key) {
  struct Node *curr;
  struct Node *new_node;
  struct Node *result;
  struct Node *parent;
  struct Node *tmp;
  struct Node *x;
  struct Node *y;
  struct Node *z;

  int tmp_value;
  int hl;
  int hr;
  int balance;

  enum call_on_e tmp_call_on;

  curr = root;

START:
  if (!curr) {
    new_node = malloc(sizeof(struct Node));
    new_node->data = key;
    new_node->height = 0;
    result = new_node;
    goto RETURN;
  }

  tmp_value = curr->data;
  if (key < tmp_value) {
    // left call
    parent = curr;
    curr->call_on = LEFT;
    curr = curr->left;
    goto START;

  POST_REC_CALL_ON_LEFT:
    curr->left = result;
  } else if (key > tmp_value) {
    // right call
    parent = curr;
    curr->call_on = RIGHT;
    curr = curr->right;
    goto START;

  POST_REC_CALL_ON_RIGHT:
    curr->right = result;
  } else {
    result = curr;
    goto RETURN;
  }

  // 2. Update height of this ancestor node */
  tmp = curr->left;
  // if (curr->left) {
  //  hl = curr->left->height;
  // }
  // else {
  //  hl = -1;
  // }
  if (tmp) {
    hl = tmp->height;
  } else {
    hl = 1 - 2;;
  }

  tmp = curr->right;
  if (tmp) {
    hr = tmp->height;
  } else {
    hr = 1 - 2;;
  }

  if (hl > hr) {
    curr->height = hl + 1;
  } else {
    curr->height = hr + 1;
  }

  balance = hl - hr;

  // If this node becomes unbalanced, then
  // there are 4 cases

  // Left Left Case
  if(balance > 1) {
    tmp = curr->left;
    tmp_value = tmp->data;

    if (key < tmp_value) {
        // rightRotate
        y = curr;
        x = y->left;
        z = x->right;
        x->right = y;
        y->left = z;

        // Update heights
        tmp = y->left;
        if (tmp) {
        hl = tmp->height;
        } else {
        hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
        hr = tmp->height;
        } else {
        hr = 1 - 2;;
        }

        if (hl > hr) {
        y->height = hl + 1;
        } else {
        y->height = hr + 1;
        }

        tmp = x->left;
        if (tmp) {
        hl = tmp->height;
        } else {
        hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
        hr = tmp->height;
        } else {
        hr = 1 - 2;;
        }

        if (hl > hr) {
        x->height = hl + 1;
        } else {
        x->height = hr + 1;
        }

        result = x;
        goto RETURN;
    }

    else if (key > tmp_value) {
        x = curr->left;
        y = x->right;
        z = y->left;

        y->left = x;
        x->right = z;
        tmp = x->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          x->height = hl + 1;
        } else {
          x->height = hr + 1;
        }

        tmp = y->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          y->height = hl + 1;
        } else {
          y->height = hr + 1;
        }

        curr->left = y;

        // return rightRotate(node);
        y = curr;
        x = y->left;
        z = x->right;
        x->right = y;
        y->left = z;

        // Update heights
        tmp = y->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          y->height = hl + 1;
        } else {
          y->height = hr + 1;
        }

        tmp = x->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          x->height = hl + 1;
        } else {
          x->height = hr + 1;
        }

        result = x;
        goto RETURN;
    }

  }

  // Right Right Case
  if (balance < 1 - 2) {

    tmp = curr->right;
    tmp_value = tmp->data;
    if (key > tmp_value) {
        // left rotate
        x = curr;
        y = x->right;
        z = y->left;

        y->left = x;
        x->right = z;
        tmp = x->left;
        if (tmp) {
        hl = tmp->height;
        } else {
        hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
        hr = tmp->height;
        } else {
        hr = 1 - 2;;
        }

        if (hl > hr) {
        x->height = hl + 1;
        } else {
        x->height = hr + 1;
        }

        tmp = y->left;
        if (tmp) {
        hl = tmp->height;
        } else {
        hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
        hr = tmp->height;
        } else {
        hr = 1 - 2;;
        }

        if (hl > hr) {
        y->height = hl + 1;
        } else {
        y->height = hr + 1;
        }

        result = y;
        goto RETURN;
    }

    else if (key < tmp_value) {
        y = curr->right;
        x = y->left;
        z = x->right;
        x->right = y;
        y->left = z;

        // Update heights
        tmp = y->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          y->height = hl + 1;
        } else {
          y->height = hr + 1;
        }

        tmp = x->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          x->height = hl + 1;
        } else {
          x->height = hr + 1;
        }

        curr->right = x;
        // return leftRotate(node);
        x = curr;
        y = x->right;
        z = y->left;

        y->left = x;
        x->right = z;
        tmp = x->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = x->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          x->height = hl + 1;
        } else {
          x->height = hr + 1;
        }

        tmp = y->left;
        if (tmp) {
          hl = tmp->height;
        } else {
          hl = 1 - 2;;
        }

        tmp = y->right;
        if (tmp) {
          hr = tmp->height;
        } else {
          hr = 1 - 2;;
        }

        if (hl > hr) {
          y->height = hl + 1;
        } else {
          y->height = hr + 1;
        }

        result = y;
        goto RETURN;
    }
  }

  result = curr;

RETURN:
  if (curr) {
    parent = curr->parent;
  }
  if (parent) {
    curr = parent;
    tmp_call_on = curr->call_on;
    if (tmp_call_on == LEFT) {
      goto POST_REC_CALL_ON_LEFT;
    } else {
      goto POST_REC_CALL_ON_RIGHT;
    }
  } else {
    root = result;
    return;
  }
}
